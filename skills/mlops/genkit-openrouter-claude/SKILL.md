---
name: genkit-openrouter-claude
description: "Genkit (JS/TS) + OpenRouter Claude: setup + region-403/proxy fix."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Genkit, OpenRouter, Claude, Proxy, Node]
    related_skills: []
---

# Genkit (JS/TS) + OpenRouter-proxied Claude

Set up a Firebase Genkit (JS/TS) project that talks to Claude (or any model) through
**OpenRouter's OpenAI-compatible endpoint**, and fix the two non-obvious failures that
otherwise eat hours: the silent `provider`-field stripping and the infamous
`403 This model is not available in your region.`

## When to Use

- Initializing a Genkit JS/TS project that uses OpenRouter instead of Google Gemini.
- Building an **Angular 19 SSR full-stack app** with a Genkit flow backend (per the official
  `genkit-angular-starter-kit`) and OpenRouter/Claude instead of Gemini — see
  `references/angular-ssr-integration.md` for the scaffold-merge workflow, Express `/chatFlow`
  wiring, the Angular-strict-mode build pitfalls (TS4111, CommonJS allowlist), and a **Mock-mode
  pattern** (`npm run mock`) that previews the full app with no API key — including the esbuild
  top-level-await build-breaker and its lazy-handler workaround.
- You call an OpenRouter model from Genkit/Node and get `403 ... not available in your region`
  even though `curl`/Python to the same endpoint works fine.
- You want OpenRouter's `provider` routing (pin/exclude upstream providers) to actually
  reach the request body from Genkit.

## Key Facts (read first — saves the whole debug)

1. **OpenRouter speaks OpenAI-compatible.** Use `@genkit-ai/compat-oai`'s `openAICompatible`
   plugin + `compatOaiModelRef` (NOTE: docs sometimes write `modelRef`, but the real export
   is `compatOaiModelRef`). `baseURL: https://openrouter.ai/api/v1`.

2. **Node's built-in `fetch` (undici) does NOT read `HTTP_PROXY`/`HTTPS_PROXY` env vars.**
   It connects directly. If the machine relies on a local proxy (Clash, etc.) to reach an
   allowed region, `curl` and Python (urllib) go through the proxy and succeed, but Genkit's
   Node `fetch` bypasses it → direct egress IP lands in a blocked region →
   `403 This model is not available in your region.` **This is the #1 cause of that 403** and
   it masquerades as a model-name / API-key / account-region problem. It is NOT.

3. **Genkit strips unknown config fields via the model's Zod `configSchema`.** OpenRouter's
   `provider` routing object is not in the default schema, so it gets dropped before the
   request is built — unless you pass a custom `configSchema` that includes (or `.passthrough()`s)
   it. The plugin DOES forward unknown fields to the body (`body = {...body, ...restOfConfig}`),
   the bottleneck is purely the schema validation upstream.

4. **Model availability is per-region AND per-upstream-provider.** On OpenRouter a model like
   `anthropic/claude-sonnet-4` may be region-blocked while `claude-sonnet-4.5` /
   `claude-opus-4.x` route to Amazon Bedrock or Anthropic and work. Always probe with the real
   key before committing to a model id.

## Diagnosis Flow (when you hit the 403)

Do this in order — it isolates the cause in ~3 steps instead of guessing:

1. **Compare egress IP across runtimes.** This is the decisive test:
   ```bash
   curl -s https://api.ipify.org; echo                    # curl egress
   python -c "import urllib.request;print(urllib.request.urlopen('https://api.ipify.org').read().decode())"
   node -e "fetch('https://api.ipify.org').then(r=>r.text()).then(console.log).catch(e=>console.log('ERR',e.message))"
   env | grep -i proxy                                     # is a proxy configured?
   ```
   If curl/Python show one IP (or succeed) and Node shows a different IP / `ERR fetch failed`,
   **it's the proxy issue (Fact #2)** → apply the ProxyAgent fix below. Done.

2. **If IPs match and Node still 403s**, reproduce with raw Python including the exact same
   body (model, messages, `provider`, `response_format`, `stream`). If raw Python succeeds with
   identical body, it's still the transport/egress layer, not the payload.

3. **Probe model availability** with the real key (see `scripts/probe_models.py`) to confirm the
   model id is region-OK and see which upstream provider it routes to.

Avoid jumping to "change the model name" or "the key is wrong" first — verify egress IP first.

## The Fix: route Node fetch through the proxy

Install undici (Node bundles it internally but it's not require-able as a module by default):

```bash
npm install undici
```

Pass a proxy-aware `fetch` to the plugin. Reads the system proxy env var; falls back to plain
fetch when no proxy is set (so it's portable across machines):

```ts
import { ProxyAgent } from 'undici';

const proxyUrl =
  process.env.HTTPS_PROXY || process.env.https_proxy ||
  process.env.HTTP_PROXY  || process.env.http_proxy;

// `any` avoids a TS2322: undici's fetch signature is narrower than global fetch's.
const proxyFetch: any = proxyUrl
  ? (input: any, init?: any) =>
      fetch(input, { ...init, dispatcher: new ProxyAgent(proxyUrl) } as any)
  : fetch;

const ai = genkit({
  plugins: [
    openAICompatible({
      name: 'openrouter',
      apiKey: process.env.OPENROUTER_API_KEY,
      baseURL: 'https://openrouter.ai/api/v1',
      fetch: proxyFetch,
    }),
  ],
});
```

Verify the proxy actually changes Node's egress:
```bash
node -e "const {ProxyAgent}=require('undici');fetch('https://api.ipify.org',{dispatcher:new ProxyAgent('http://127.0.0.1:7890')}).then(r=>r.text()).then(t=>console.log('via proxy:',t))"
```

## Optional: enable OpenRouter `provider` routing from Genkit

Only needed if you want to pin/exclude upstream providers (e.g. force Amazon Bedrock, forbid
fallback to a region-blocked Anthropic upstream). Pass a custom `configSchema`:

```ts
const OpenRouterConfigSchema = z.object({
  temperature: z.number().min(0).max(2).optional(),
  provider: z.object({
    order: z.array(z.string()).optional(),
    allow_fallbacks: z.boolean().optional(),
  }).optional(),
}).passthrough();           // .passthrough() lets any other OpenRouter-specific field through

const claude = compatOaiModelRef({
  name: 'openrouter/anthropic/claude-opus-4.8',
  configSchema: OpenRouterConfigSchema,
});

// then in ai.generate:
//   config: { temperature: 0.8, provider: { order: ['Amazon Bedrock'], allow_fallbacks: false } }
```

NOTE: if the real cause is the proxy (Fact #2), provider pinning will NOT fix the 403 — the
request never leaves the right egress. Fix the proxy first.

## Recommended Project Wiring

- **Model id from env** so you can switch without editing code:
  ```ts
  const modelName = process.env.OPENROUTER_MODEL || 'anthropic/claude-opus-4.8';
  const claude = compatOaiModelRef({ name: `openrouter/${modelName}` });
  console.log(`[genkit] using model: ${modelName}`);
  ```
  Run-time override: `OPENROUTER_MODEL=anthropic/claude-sonnet-4.5 npm start`
- **Secrets in `.env`** (gitignored) loaded via `import 'dotenv/config'`; commit a `.env.example`
  template. Document the optional `HTTPS_PROXY` and `OPENROUTER_MODEL` keys there.
- **tsconfig** with `process.env` usage needs `"types": ["node"]` + `npm i -D @types/node`,
  otherwise `tsc` errors on `process`.
- **Run a one-shot script** with `node --import tsx src/index.ts` (or `npm start` mapped to it);
  `npm run genkit:ui` for the dev UI.

## Pitfalls

- `npm start` for a one-shot Genkit script (tsx) exits when done — orchestration layers may
  misclassify it as a long-lived server and block it. Run via
  `node --import tsx src/index.ts` directly if a wrapper refuses `npm start`.
- The `fetch:` option type-mismatches global fetch (TS2322). Type the wrapper as `any` — do not
  fight the types; undici's signature is intentionally narrower.
- Don't assume a model id doesn't exist just because you haven't seen it — list them live
  (`/api/v1/models`) before deciding. (e.g. `claude-opus-4.8` is real.)
- On Windows/MSYS, system `HTTPS_PROXY` is usually already set (Clash 127.0.0.1:7890); the code
  above picks it up automatically, so `.env` need not duplicate it.
- Region/provider mapping observed (subject to change): `claude-opus-4.0/4.1/4.5` → Amazon
  Bedrock; `claude-opus-4.6/4.7/4.8` (+ `-fast`) → Anthropic; `claude-sonnet-4` was
  region-blocked while `claude-sonnet-4.5` worked via Bedrock.

> **Angular SSR builds:** The per-request ProxyAgent dispatcher approach above breaks when
> Angular's esbuild bundles undici — the bundled undici's private Symbols don't match Node's
> built-in undici, causing `TypeError: Expected a private symbol`. For SSR apps, use
> `setGlobalDispatcher` in `server.ts` instead. See `genkit-openrouter-app` skill, Pitfall 6
> for the full fix (externalize undici + global dispatcher + plain fetch).

## Verification Checklist

1. `npx tsc --noEmit` → exit 0.
2. `node --import tsx src/index.ts` → real model output (not a 403).
3. Toggle model via `OPENROUTER_MODEL=... ` and confirm the startup log line changes.
4. If a proxy is involved, the undici egress-IP one-liner returns the allowed region's IP.
