# Undici Private Symbol Mismatch — Full Reproduction

## The error

After `ng build` and starting `node dist/app/server/server.mjs`:

```
TypeError: Expected a private symbol
    at node:internal/deps/undici/undici:...
```

No stack trace points to user code — the error originates deep inside Node's internal undici.

## Why it happens

1. Angular's esbuild inlines `undici` into the server chunk.
2. Node.js ≥21 ships with built-in `undici` (used by native `fetch`).
3. Bundled undici creates fresh instances of `Symbol.for('undici.client')` and
   `Symbol.for('undici.dispatcher')`.
4. When a ProxyAgent created from bundled undici is passed as `dispatcher` to Node's
   native `fetch`, the runtime checks the dispatcher's private Symbol against its own
   built-in undici's symbols → mismatch → throws.

## Conditions that trigger it

- Angular 19+ SSR with `@angular-devkit/build-angular:application` builder
- `import { ProxyAgent } from 'undici'` in a source file that gets bundled
- Passing `dispatcher: new ProxyAgent(url)` to `fetch()` (either per-request or via
  the Genkit plugin's `fetch` option)

## The fix (three parts)

### A. `angular.json` — externalize undici
```jsonc
"externalDependencies": ["undici"]
```

### B. `src/server.ts` — setGlobalDispatcher at startup
```ts
if (proxyUrl) {
  import('undici').then(({ ProxyAgent, setGlobalDispatcher }) => {
    setGlobalDispatcher(new ProxyAgent({ uri: proxyUrl, ... }));
  });
}
```

### C. `src/flows.ts` — use bare fetch
```ts
const proxyFetch: any = fetch; // global dispatcher handles proxy
```

## How NOT to fix (dead ends)

- ❌ Don't set `dispatcher` in `flows.ts` — the bundle still has a mismatched ProxyAgent.
- ❌ Don't try to import undici conditionally without externalizing — same Symbol mismatch.
- ❌ Don't use `--external:undici` CLI flag — won't work with Angular CLI builder.

## Verification

After the fix, the built server starts cleanly:
```
$ npm run mock
Node Express server listening on http://localhost:4000
[genkit] ⚠️ MOCK 模式已启用 ...
$ curl -s -X POST localhost:4000/chatFlow -H 'content-type: application/json' \
    -d '{"data":{"userInput":"你好","sessionId":"test","clearSession":true}}'
{"result":{"agentResponse":"你好！我是一个演示用的聊天助手...","options":[...]}}
```

No `TypeError`, no `Expected a private symbol`, and the flow endpoint returns proper JSON.
