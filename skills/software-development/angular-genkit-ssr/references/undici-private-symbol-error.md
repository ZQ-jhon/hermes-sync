# Undici Private Symbol Error — Full Transcript

## Reproduction

```bash
cd ~/project/a2ui-angular
# Ensure flows.ts imports ProxyAgent from 'undici' and passes it to fetch
ng build
PORT=4000 node dist/app/server/server.mjs
```

## Error Output

```
TypeError: Expected a private symbol
    at node:internal/deps/undici/undici:...
    at new ProxyAgent (...)
    at ...
```

## Why It Happens

1. Angular SSR builder (`@angular-devkit/build-angular:application`) resolves `import { ProxyAgent } from 'undici'` at build time and **bundles** the full `undici` package into `dist/app/server/` chunk files.

2. Node.js 21+ ships its own `undici` internally (`node:internal/deps/undici/undici`). The native `fetch()` uses this built-in instance.

3. The bundled undici and Node's built-in undici are **different instances**. Each maintains its own set of private Symbols — `Symbol.for('undici.client')` and friends.

4. When the SSR server constructs a `ProxyAgent` from the **bundled** undici and passes it as `dispatcher` to `fetch()`, Node's native fetch tries to read private Symbols on the ProxyAgent using its own Symbol registry. The Symbols don't match → `TypeError: Expected a private symbol`.

## Solution Chain

1. `externalDependencies: ["undici"]` in `angular.json` → Angular leaves `import('undici')` as-is, loaded at runtime
2. `setGlobalDispatcher(new ProxyAgent({uri: proxyUrl}))` in `server.ts` → sets a global dispatcher from the **real** undici
3. `flows.ts` uses `fetch` without custom dispatcher → goes through the global dispatcher → works
