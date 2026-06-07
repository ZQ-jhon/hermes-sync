---
name: angular-genkit-ssr
description: Angular 19+ SSR with Genkit flows — bundler pitfalls, proxy setup, mock patterns, and debugging /chatFlow 404s.
---

# Angular SSR + Genkit

Triggers: Angular project with Genkit flows, `ng serve` not showing flow responses, undici bundling errors in SSR, `/chatFlow` endpoint debugging, OpenRouter proxy setup in Angular SSR.

## Core Pitfall: `ng serve` does not mount Express routes

`ng serve` uses `@angular-devkit/build-angular:dev-server`. It serves the Angular frontend but does **not** run `server.ts` or its Express routes. Any Genkit flow endpoint (e.g. `POST /chatFlow`) will return 404 or 502.

**Always test flows with the SSR build product:**

```bash
ng build && node dist/app/server/server.mjs
# or with env:
MOCK_LLM=1 PORT=4242 node dist/app/server/server.mjs
```

Only the Express server in `server.ts` (started via `node dist/app/server/server.mjs`) actually mounts `/chatFlow`.

## Undici Bundling Conflict (Angular SSR)

**Symptom:** `TypeError: Expected a private symbol` at `node:internal/deps/undici/undici:...` when the SSR server starts.

**Root cause:** Angular's `application` builder bundles `undici` into the server chunk. The bundled `undici`'s private Symbols (e.g. `Symbol.for('undici.client')`) don't match Node.js's built-in `undici` instance. When you pass a ProxyAgent from the bundled undici to Node's native `fetch()`, they clash.

**Fix — two parts:**

### 1. Externalize undici in `angular.json`

```json
"architect": {
  "build": {
    "options": {
      "externalDependencies": ["undici"]
    }
  }
}
```

This tells Angular to `import('undici')` at runtime from `node_modules`, not bundle it.

### 2. Use `setGlobalDispatcher` instead of per-request dispatcher

Do NOT pass a custom `dispatcher` / `ProxyAgent` to individual `fetch()` calls. The bundled-flow code can't construct a ProxyAgent that Node's native fetch understands. Instead, set a global dispatcher once at server startup:

```js
// server.ts — BEFORE any flow modules are imported
import('undici').then(({ ProxyAgent, setGlobalDispatcher }) => {
  setGlobalDispatcher(new ProxyAgent({
    uri: process.env['HTTPS_PROXY'] || 'http://127.0.0.1:7890',
    connectTimeout: 60_000,
    headersTimeout: 120_000,
    bodyTimeout: 120_000,
  }));
});
```

Then in `flows.ts`, pass `fetch` directly (no dispatcher):
```js
const proxyFetch = fetch; // global dispatcher handles proxy
```

### Why this works

`setGlobalDispatcher` is called at runtime with the **real** undici from `node_modules`. All subsequent `fetch()` calls (including those from the bundled flow code) go through Node's native fetch, which uses the globally-registered dispatcher — a real undici instance with matching private Symbols.

## Mock Flow Pattern

For zero-API-key local preview, use `MOCK_LLM` env var to switch flows:

```js
// server.ts
const useMock = !!process.env['MOCK_LLM'];
async function getChatHandler() {
  const mod = useMock ? await import('./flows.mock') : await import('./flows');
  return expressHandler(mod.chatFlow);
}
```

Mock flow (`flows.mock.ts`):
- Same `defineFlow` signature, input/output schemas as real flow
- `genkit({})` — no plugins, no network calls
- Pure rule-based responses with simulated delay (120–420ms)
- Import nothing from undici, openai-compat, etc.

## Genkit SSE Streaming

Genkit's `expressHandler` wraps flow responses in SSE when `Accept: text/event-stream`:
```
data: {"result":{"agentResponse":"...","options":[...]}}
```

Non-streaming flows (like mock) return a single SSE event. Real flows with `chat.send()` stream token-by-token through the same SSE envelope.

## Package.json Scripts

```json
{
  "mock": "ng build && cross-env MOCK_LLM=1 node dist/app/server/server.mjs",
  "mock:dev": "cross-env MOCK_LLM=1 ng serve",
  "mock:ssr": "cross-env MOCK_LLM=1 node dist/app/server/server.mjs",
  "start:with-genkit-ui": "ng build && cross-env NO_PROXY=localhost,127.0.0.1 genkit start -- node dist/app/server/server.mjs"
}
```

- `mock` / `mock:ssr` — full SSR build + server, `/chatFlow` works
- `mock:dev` — `ng serve` only, no `/chatFlow`, frontend-only debugging
- `start:with-genkit-ui` — real OpenRouter flow with Genkit UI, SSR mode

## Related Skills

- `clash-proxy` — Clash API port discovery, node switching, TLS diagnosis. Load when proxy isn't working or you need to switch exit nodes.

## References

- `references/undici-private-symbol-error.md` — full error transcript and reproduction recipe
