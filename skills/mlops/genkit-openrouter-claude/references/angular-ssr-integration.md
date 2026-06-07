# Integrating Genkit + OpenRouter/Claude into an Angular 19 SSR app

When the target is not a standalone Node script but a full-stack **Angular 19 SSR**
application (per the official `genkit-angular-starter-kit`), the backend flow setup is
identical to the main SKILL.md — same `openAICompatible` plugin, same undici `ProxyAgent`
fetch — but there are several integration-specific steps and Angular-strict-mode pitfalls
that otherwise cost a build cycle each.

## Scaffolding workflow (in-place conversion of an existing repo)

`ng new` refuses to run in a non-empty dir (existing `.git`/`.env`/`src`). To convert an
existing repo in place without losing git history or secrets:

1. Generate the scaffold in a temp dir, non-interactively:
   ```bash
   npx -y -p @angular/cli@19 ng new app --ssr --style=scss --skip-git --defaults
   ```
   (`--skip-git` because you're merging into an existing repo. `npx -p` avoids a global install.)
2. Tag a rollback point first: `git tag -f pre-angular-scaffold`.
3. Copy scaffold files into the project, **protecting** `.git`, `.env`, `.env.example`,
   `.gitignore` (merge manually), and any backend source. Back up the old entry script
   (e.g. `src/index.ts` → `src/_legacy-*.ts.bak`, gitignored) — git history already has it.
4. Merge `package.json`: keep Angular's deps/scripts, ADD backend deps
   (`genkit`, `@genkit-ai/compat-oai`, `@genkit-ai/express`, `undici`, `dotenv`,
   `partial-json`, `zod`, `@angular/material`). **Use Angular's TypeScript (`~5.7.x`), not a
   newer major** — Angular 19 doesn't support TS 6.
5. `rm package-lock.json && npm install` so the lock reflects the merged manifest.

## Wiring the flow into Express SSR (`src/server.ts`)

Angular 19.2.x scaffolds `server.ts` with the **`CommonEngine`** style (`@angular/ssr/node`,
`isMainModule`). The starter-kit's own `server.ts` may use the newer `AngularNodeAppEngine`
API — **do not blindly copy it**; base your edits on the version `ng new` actually emitted so
it matches the installed runtime. Just insert the flow endpoint before the static/SSR catch-all:

```ts
import { expressHandler } from '@genkit-ai/express';
import { chatFlow } from './flows';

app.use(express.json());              // flow endpoint needs JSON body parsing
app.post('/chatFlow', expressHandler(chatFlow));   // BEFORE the app.get('**', ...) routes
// ... then the existing express.static + commonEngine.render catch-alls
```

The Angular client calls it via `runFlow({ url: '/chatFlow', input: {...} })` from
`genkit/beta/client` inside an `AgentService` (`resource()` + `linkedSignal()`).

## SSR config alignment

- 19.2.x scaffolds `app.config.server.ts` with only `provideServerRendering()`. To use the
  starter-kit's `app.routes.server.ts` (first route `RenderMode.Client`, `**` → `Server`),
  add `provideServerRouting(serverRoutes)` back to that config. Client-rendering the home
  route avoids running `resource()` loaders (which fire the flow request) during SSR.
- Add `provideAnimationsAsync()` to `app.config.ts` for Angular Material components
  (`MatProgressBar`, etc.) — SSR-safe.
- Delete the scaffold's empty `app.routes.ts` and `app.component.spec.ts` if the root
  component just renders `<app-agent-chat />` with no client router.

## Angular-strict-mode pitfalls (these are the build-breakers)

1. **`TS4111`: `process.env.FOO` is forbidden.** Angular's default `tsconfig.json` sets
   `noPropertyAccessFromIndexSignature: true`, so every `process.env.X` must become
   `process.env['X']`. This bites the backend `flows.ts` ported from a loose-tsconfig Node
   project. Fix ALL of them (`HTTPS_PROXY`, `http_proxy`, `OPENROUTER_API_KEY`,
   `OPENROUTER_MODEL`, ...) — the build reports them one or two at a time, so don't stop at
   the first.

2. **CommonJS bailout WARNINGS from genkit/openai deps.** `ng build` warns that
   `uri-templates`, `@opentelemetry/sdk-node`, `dotprompt`, `agentkeepalive`, `whatwg-url`,
   `encoding`, `web-streams-polyfill` are not ESM. These are warnings, not errors — silence
   them by listing them under `architect.build.options.allowedCommonJsDependencies` in
   `angular.json`.

3. **`patch`/single-file `tsc` lint false-positives.** Editing `flows.ts`/`server.ts` triggers
   the edit tool's bare-`tsc` check, which reports `TS1259 handlebars`, `TS2307
   @genkit-ai/core/async`, `TS18028 private identifiers` from genkit/openai `.d.ts` files.
   These are NOT real — `ng build` uses esbuild + Angular compiler + `skipLibCheck` and does
   not hit them. **Trust `ng build`, not the per-edit lint, for genkit-in-Angular projects.**

## Mock mode — preview the app with NO API key (`npm run mock`)

For an open-source repo, anyone who clones it but has no OpenRouter key can't experience the
app. Add a **Mock flow** so `npm run mock` previews the full UI/interaction with zero key and
zero network calls — "所见即所得". The user preference here was explicit: don't auto-detect or
add env-toggle complexity, just expose a dedicated `mock` npm script.

Design rule: the mock must have the **same flow name, same input/output Zod schema, same return
shape** (`{agentResponse, options}`) as the real `chatFlow`, so the frontend, the `/chatFlow`
endpoint, loading bars, and option chips all work unchanged.

1. `src/flows.mock.ts` — a rule-based fake `chatFlow`. Use a minimal `genkit({})` instance (no
   model plugin → no network). Replicate any tool behaviour locally (e.g. a `getDateTime` branch
   that returns the real `new Date()` formatted identically). Keep a tiny in-memory
   `Map<sessionId, turn>` to simulate multi-turn; honour `clearSession`. Add a small
   `setTimeout` (~120–420ms) so the frontend loading bar is visible.
2. `package.json` scripts (use `cross-env` for cross-platform env vars — Windows-safe):
   ```json
   "mock":     "cross-env MOCK_LLM=1 ng serve",
   "mock:ssr": "cross-env MOCK_LLM=1 node dist/app/server/server.mjs"
   ```
3. `src/server.ts` selects real vs mock flow by the `MOCK_LLM` env var.

### CRITICAL build pitfall: esbuild forbids top-level `await` in the server bundle

The obvious `const { chatFlow } = MOCK ? await import('./flows.mock') : await import('./flows')`
**fails the `ng build`** with a REAL error (not a lint false-positive):
`Top-level await is not available in the configured target environment`. Angular's server bundle
is built for a target that disallows TLA even though tsconfig is ES2022. Workaround: defer the
dynamic import into a **lazy async handler** invoked on first request — no top-level await:

```ts
const useMock = !!process.env['MOCK_LLM'];
let chatHandler: ((req: any, res: any, next: any) => void) | undefined;
async function getChatHandler() {
  if (!chatHandler) {
    const mod = useMock ? await import('./flows.mock') : await import('./flows');
    chatHandler = expressHandler(mod.chatFlow as any);
  }
  return chatHandler;
}
app.post('/chatFlow', async (req, res, next) => {
  try { (await getChatHandler())(req, res, next); } catch (err) { next(err); }
});
```

Bonus: lazy import means mock mode never even loads `flows.ts`, so the real OpenRouter plugin is
never initialised and no key is needed.

### Verifying mock mode

`cross-env` lives in `node_modules/.bin`, so it's only on PATH inside `npm run`. When testing the
built SSR server by hand from a bare shell, set the env var directly instead:
`MOCK_LLM=1 PORT=4200 node dist/app/server/server.mjs`. Then curl `/chatFlow` and confirm the
`{agentResponse, options}` shape comes back. NOTE: passing CJK text through curl in git-bash/MSYS
mojibakes (wrong console encoding) — that's a shell artifact, not a server bug; verify CJK
branches with a UTF-8 Python `urllib` request instead.

## `.gitignore` additions

Angular adds build artifacts to ignore on top of the Node ones: `.angular/` (build cache),
`dist/`. Keep `.env` and `.genkit/` ignored.

## Verification (end-to-end)

`outputPath` defaults to `dist/app`, so the SSR server is `dist/app/server/server.mjs`.

```bash
HTTPS_PROXY=http://127.0.0.1:7890 npx ng build           # expect: build OK, only CJS warnings
PORT=4100 HTTPS_PROXY=http://127.0.0.1:7890 node dist/app/server/server.mjs &   # 4000 may be in use
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" --noproxy '*' http://127.0.0.1:4100/   # 200 (SSR home)
curl -s --noproxy '*' -X POST http://127.0.0.1:4100/chatFlow \
  -H 'Content-Type: application/json' \
  -d '{"data":{"userInput":"What is the date and time?","sessionId":"t1","clearSession":true}}'
# expect: {"result":{"agentResponse":"...","options":[...]}} and date/time tool actually fires
```

Use `--noproxy '*'` on curl when a system proxy is set, so localhost requests don't get routed
through Clash. Pass `--noproxy` consistently or the local call fails.

## Pitfalls specific to this integration

- Port 4000 is the SSR default; a leftover Genkit-UI / prior server process often holds it
  (`EADDRINUSE`). Test on an alternate port (`PORT=4100`) rather than hunting the holder.
- Node 26 prints `Unsupported` against Angular 19 (officially ≤22) but builds and runs fine —
  it's a CLI warning, not a blocker.
- The flow's structured-JSON output is parsed with `partial-json`'s `parse()` after stripping
  a possible ```json fence; keep that helper when porting `chatFlow`.
