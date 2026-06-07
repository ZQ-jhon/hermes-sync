# Angular SSR + Genkit flow as a custom Express route

When a Genkit flow lives inside an Angular 17+ SSR app, you expose it by adding a route to
the Express app in the SSR server entry. This file captures the non-obvious dev-server trap
and the verified working setup.

## Architecture
- `angular.json` → `architect.build.options.ssr.entry: "src/server.ts"`.
- `src/server.ts` builds an Express `app`, runs Angular's `CommonEngine` for HTML SSR, AND
  mounts custom API routes, e.g.:
  ```ts
  app.post('/chatFlow', express.json(), async (req, res) => {
    const handler = await getChatHandler();   // lazy: picks real vs mock flow by MOCK_LLM
    res.json(await handler(req.body));
  });
  ```
- A lazy `getChatHandler()` that switches flow implementation by an env var (e.g. `MOCK_LLM`)
  lets the same server binary serve a mock flow (no model calls) or the real Genkit flow.

## The trap: `ng serve` ≠ built SSR
| Runner | Page render | `POST /chatFlow` |
|--------|-------------|------------------|
| `ng serve` (dev server) | 200 OK | **404 or 502** |
| `ng build && node dist/<app>/server/server.mjs` | 200 OK | **200 OK** |

- Under `ng serve`, compilation is clean and the flows-mock chunk is generated, but the
  Vite/dev SSR middleware does not reliably register `src/server.ts`'s custom Express routes.
  Observed: first `POST /chatFlow` → 404 (route absent); after a reload the dev SSR runtime
  crashes → 502 with **no stack in the logs** (the dev server swallows the exception).
- This looks like a routing/flow bug but is purely a dev-server-vs-built-bundle difference.

## Known-good npm scripts
```jsonc
{
  "preview":     "ng build && cross-env MOCK_LLM=1 node dist/app/server/server.mjs", // serves /chatFlow
  "preview:dev": "cross-env MOCK_LLM=1 ng serve",   // front-end only — /chatFlow WILL 404
  "preview:ssr": "node dist/app/server/server.mjs"  // serve an already-built bundle
}
```
`PORT` env var overrides the listen port (default 4000). `cross-env` keeps it Windows-safe.

## Verification discipline (do not skip)
A homepage `200` says nothing about the flow endpoint. Always probe the POST endpoint and
assert on the BODY:
```bash
curl -s -X POST localhost:4000/chatFlow -H 'content-type: application/json' \
  -d '{"userInput":"我要注册","clearSession":true}'
# expect the structured flow response in the body, not just HTTP 200
```
End-to-end smoke that proved the built bundle green: homepage 200; register intent returns a
declarative form payload (phone + code fields + options); a chit-chat input falls through to
the model/mock; a "what time is it" input returns a timestamp. All four asserted on body.

**If you get `{"message":"Internal Error","status":"INTERNAL"}`:** The expressHandler
swallows the real error. Extract it by importing the built flow chunk directly from a
throwaway Node script — see Pitfall 5 in the parent SKILL.md for the one-liner recipe.

## Windows / proxy notes (this environment)
- Long-lived servers must be started as tracked background processes, not shell `&`.
- Before starting, check the port is free; dev-server child processes can outlive a killed
  npx parent, leaving stale listeners on 4000/4200/etc.
- npm installs that need network go through the local Clash proxy via a per-shell
  `export HTTPS_PROXY/HTTP_PROXY` (never written globally).
