---
name: genkit-openrouter-app
description: Build a Genkit JS (TypeScript) app backed by an OpenAI-compatible provider such as OpenRouter — proxying Claude/other models via @genkit-ai/compat-oai. Covers project init, structured output flows, passing OpenRouter-only config (provider routing), and the non-obvious Node-fetch-ignores-system-proxy region-403 trap. Use when setting up Genkit with OpenRouter/Claude, or debugging "This model is not available in your region" 403s.
---

# Genkit + OpenRouter (OpenAI-compatible) app

Set up Genkit JS to call Claude (or any model) through OpenRouter's OpenAI-compatible
endpoint. Official docs: https://genkit.dev/docs/js/get-started/ and
https://genkit.dev/docs/integrations/openai-compatible/

## Setup

```bash
npm install genkit @genkit-ai/compat-oai dotenv
npm install -D @types/node tsx typescript
# remove google-genai if you scaffolded from the Gemini quickstart:
npm uninstall @genkit-ai/google-genai
```

Minimal wiring (the import name is `compatOaiModelRef`, NOT `modelRef` as some docs show):

```ts
import 'dotenv/config';
import { genkit, z } from 'genkit';
import { openAICompatible, compatOaiModelRef } from '@genkit-ai/compat-oai';

const ai = genkit({
  plugins: [openAICompatible({
    name: 'openrouter',
    apiKey: process.env.OPENROUTER_API_KEY,
    baseURL: 'https://openrouter.ai/api/v1',
  })],
});

const claude = compatOaiModelRef({ name: 'openrouter/anthropic/claude-sonnet-4.5' });
```

- Model id format: `openrouter/<vendor>/<model>` (plugin name `/` OpenRouter model id).
- Structured output: pass `output: { schema: ZodSchema }` to `ai.generate(...)`; the plugin
  emits `response_format: json_schema`.
- Put `OPENROUTER_API_KEY` in `.env` (gitignored), ship a committable `.env.example`.
- Key from https://openrouter.ai/keys . Run with `node --import tsx src/index.ts`.

## tsconfig gotchas
If `tsconfig.json` has `verbatimModuleSyntax: true`, `module: nodenext`, `target: esnext`:
- using `process.env` requires `"types": ["node"]` AND `npm i -D @types/node`, else TS errors.
- Do NOT run `npx tsc --noEmit src/index.ts` (filenames on the CLI ignore tsconfig → TS5112).
  Run bare `npx tsc --noEmit` so the project config loads.

## Pitfall 1 — Node built-in fetch ignores HTTP(S)_PROXY → region 403 (THE BIG ONE)
Symptom: `403 This model is not available in your region.` from Genkit, while `curl` and
Python to the *same* endpoint with the *same* body/key succeed. Anthropic models on
OpenRouter are region-gated; some networks need a local proxy (Clash etc.) to reach an
allowed exit IP.

Root cause: **Node.js built-in `fetch` (undici) does NOT read `HTTP_PROXY`/`HTTPS_PROXY`
env vars** — it connects directly, so its exit IP lands in the blocked region even though
your shell tools go through the proxy. This masquerades as a model-name / API-key / account
problem; it is a transport problem.

Fix — give Genkit a proxy-aware fetch via undici `ProxyAgent`:
```bash
npm install undici
```
```ts
import { ProxyAgent } from 'undici';
const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const proxyFetch: any = proxyUrl
  ? (input: any, init?: any) =>
      fetch(input, { ...init, dispatcher: new ProxyAgent(proxyUrl) } as any)
  : fetch;

openAICompatible({ name: 'openrouter', apiKey: ..., baseURL: ..., fetch: proxyFetch });
```
Type note: the plugin's `fetch` type is narrower than the global; declare `proxyFetch: any`
to avoid a TS2322 mismatch (functional, harmless to widen).

Diagnose before fixing — compare exit IPs (see scripts/diagnose-region-403.sh):
`curl https://api.ipify.org` vs `node -e "fetch('https://api.ipify.org').then(r=>r.text()).then(console.log)"`.
If curl shows an allowed IP and Node `fetch failed`/shows a different IP → it's the proxy gap.

> **SSR / bundled builds:** The per-request `dispatcher` approach above breaks in Angular SSR
> (and any build that bundles undici) — see **Pitfall 6**. For SSR apps, use
> `setGlobalDispatcher` in `server.ts` and pass plain `fetch` to the plugin.

## Pitfall 2 — model 403 is sometimes the model, not the region
`anthropic/claude-sonnet-4` (older) was region-blocked outright in one case while
`claude-sonnet-4.5` routed to Amazon Bedrock and worked. Before deep debugging, try a newer
model id. Use scripts/diagnose-region-403.sh to probe which Claude ids actually answer.

## Pitfall 3 — OpenRouter-only config fields (e.g. `provider` routing) get stripped
Genkit validates `config` against the model's Zod `configSchema` and DROPS unknown keys, so
OpenRouter extensions like `provider: { order: [...], allow_fallbacks: false }` never reach
the request body. To pass them, give `compatOaiModelRef` a custom `configSchema` that
`.passthrough()`es and declares the field:
```ts
const schema = z.object({ provider: z.any().optional() }).passthrough();
compatOaiModelRef({ name: '...', configSchema: schema });
```
The plugin DOES splat unknown config into the request body (`{...body, ...restOfConfig}` in
node_modules/@genkit-ai/compat-oai/lib/model.js `toOpenAIRequestBody`) — the only gate is the
schema. NOTE: in the region-403 case above, provider routing was a red herring; the real fix
was the proxy. Reach for passthrough config only when you genuinely need an OpenRouter-only
parameter.

## Reducing model calls — flow caching layer
To cut LLM calls in a flow, see references/flow-caching-layer.md: a reusable
**normalize → template hot-path bypass → single-turn cache → model → write-back** pattern
with a Redis backend that auto-degrades to an in-process LRU (so a clone with no Redis still
runs). Includes the intent-template registry (register/login forms returned with 0 model
calls, no PII), SHA-256 key shape, the safety boundary (never cache multi-turn / PII), and
ioredis wiring gotchas (`retryStrategy: () => null`, dynamic import, CommonJS allowlist).

## Pitfall 4 — Angular SSR: `ng serve` does NOT mount your custom Express routes
When you embed a Genkit flow in an Angular 17+ SSR app, the flow is exposed by adding an
`app.post('/chatFlow', ...)` (or similar) to the Express app in the SSR entry
(`src/server.ts`, wired via `angular.json` `ssr.entry`). The trap: the **`ng serve` dev
server does NOT reliably mount these custom Express routes** — the page renders fine but
`POST /chatFlow` returns **404 (route never registered) or 502 (dev-server SSR middleware
crashes and swallows the stack)**, while compilation looks perfectly clean. The custom
Express routes only work when you run the **built SSR bundle**:
```bash
ng build && node dist/<app>/server/server.mjs   # PORT defaults to 4000
```
So any npm script that previews/serves the flow endpoint must run the build product, not
`ng serve`. Recommended split:
- `"preview": "ng build && node dist/app/server/server.mjs"`  ← the one that actually serves /chatFlow
- `"preview:dev": "ng serve"`                                   ← front-end-only, /chatFlow will 404

VERIFICATION DISCIPLINE (the lesson that cost the time): a homepage `200` proves NOTHING
about the flow endpoint. Always probe the actual POST endpoint
(`curl -X POST localhost:4000/chatFlow -d '...'` or a Python request) and assert on the
response body, not just the status. See references/angular-ssr-genkit-flow.md for the full
reproduction (404/502 under ng serve, green under built SSR) and a known-good script split.

## Pitfall 6 — Angular SSR bundles undici → private Symbol mismatch (TypeError: Expected a private symbol)

Symptom: after `ng build`, starting `node dist/app/server/server.mjs` crashes with:

```
TypeError: Expected a private symbol
    at node:internal/deps/undici/undici:...
```

**Root cause:** Angular's esbuild bundles `undici` into the SSR server chunk. At runtime,
Node.js has its own built-in undici (used by native `fetch`). The bundled copy carries
*different instances* of undici's private `Symbol.for('undici.client')` — when you pass
`dispatcher: new ProxyAgent(url)` to fetch, it checks the dispatcher's private Symbol
against the runtime's, finds a mismatch, and throws.

This happens even when the build is otherwise clean (no TS errors, no import errors).

**Fix — two changes required:**

### 1. Externalize undici from the bundle (`angular.json`)

```jsonc
// angular.json → projects.<app>.architect.build.options
{
  "externalDependencies": ["undici"]
}
```

This tells esbuild to NOT inline `undici` — the runtime will load it from `node_modules`,
matching Node's built-in undici.

### 2. Use setGlobalDispatcher instead of per-request dispatcher (`server.ts`)

Per-request `dispatcher` (Pitfall 1 approach) overrides the global dispatcher and still
risks the Symbol mismatch when undici is bundled. Instead, set the global dispatcher ONCE
at server startup using a dynamic import (the dynamic import ensures undici is loaded at
runtime from node_modules, not from the bundle):

```ts
// src/server.ts — at the top, before any route or engine setup
const proxyUrl =
  process.env['HTTPS_PROXY'] || process.env['https_proxy'] ||
  process.env['HTTP_PROXY']  || process.env['http_proxy'];

if (proxyUrl) {
  import('undici').then(({ ProxyAgent, setGlobalDispatcher }) => {
    setGlobalDispatcher(new ProxyAgent({
      uri: proxyUrl,
      connectTimeout: 60_000,
      headersTimeout: 120_000,
      bodyTimeout: 120_000,
    }));
    console.log(`[server] global proxy: ${proxyUrl}`);
  });
}
```

### 3. Simplify flows.ts — use bare fetch

In `flows.ts`, drop the per-request ProxyAgent wrapper entirely:

```ts
// Was: const proxyFetch = proxyUrl ? (input, init) => fetch(input, { ...init, dispatcher: ... }) : fetch;
// Now: just pass fetch directly — global dispatcher handles proxy
const proxyFetch: any = fetch;
```

The `openAICompatible` plugin receives the plain `fetch`; the global dispatcher set by
`server.ts` routes all fetches through the proxy automatically.

**Verification:** after these changes, `ng build && node dist/app/server/server.mjs` starts
without the private Symbol error, and `POST /chatFlow` returns real model responses (not 403).

## Pitfall 5 — Genkit expressHandler returns opaque 500 "Internal Error"

When a Genkit flow exposed via `expressHandler` fails, the response is a generic
`{"message":"Internal Error","status":"INTERNAL"}` — no stack, no root cause, no console
output. This hides the real error (auth failure, proxy 403, import crash, etc.).

**Debug technique — call the flow directly from a one-off script:**

```bash
# In the project root, write a tiny script that imports the built flow chunk directly:
cat > _test_flow.mjs << 'SCRIPT'
import { chatFlow } from "./dist/app/server/chunk-<FLOW_CHUNK>.mjs";
try {
  const result = await chatFlow({ userInput: "hello", sessionId: "test", clearSession: true });
  console.log("SUCCESS:", JSON.stringify(result));
} catch (e) {
  console.error("ERROR:", e.message);
  console.error("STACK:", e.stack);
}
SCRIPT
node --no-warnings _test_flow.mjs
```

The built chunk name can be found with:
```bash
grep -l "chatFlow\|openrouter" dist/app/server/chunk-*.mjs
```

This bypasses Express and Angular entirely, revealing the real error (e.g.
`UNAUTHENTICATED: 403 This model is not available in your region.`).

**Commit discipline:** delete `_test_flow.mjs` after debugging — it's a throwaway probe, not
part of the project.

## Verification
- `npx tsc --noEmit` → exit 0.
- `node --import tsx src/index.ts` → prints the structured object.
- For SSR apps: hit `POST /chatFlow` on the BUILT bundle and assert on the body (Pitfall 4).
  If you get generic 500 "Internal Error", use Pitfall 5 to extract the real error.
- See references/openrouter-region-403-debug.md for the full elimination path that proved
  body/headers/UA/stream were NOT the cause, only the proxy.
