# Flow-level caching layer for Genkit (cut model calls)

A reusable pattern to reduce LLM calls in a Genkit `defineFlow`: **normalize → match
template (hot-path bypass) → cache lookup → call model → write back**. Backend is
Redis when available, otherwise a process-internal LRU — so a clone with no Redis still
runs. Proven on a chat flow whose contract is `{userInput, sessionId, clearSession}` →
`{agentResponse, options}`.

## Layered design (pick the layers you need)

1. **Template registry (hot-path, highest priority).** Match the *intent* of normalized
   input against pre-built templates (e.g. register/login forms). On hit: return a
   deterministic, declarative UI/answer with **0 model calls**, cross-user reusable, and
   **no PII** (the template is a skeleton; user-entered phone/code stays on the frontend
   and is submitted separately — never cached). Match is history-independent, so check it
   *before* any session/cache logic.

2. **Generic response cache (single-turn only).** Enable ONLY when the request has no
   conversation-history dependency — gate on `clearSession === true`. Multi-turn requests
   depend on history; caching them cross-talks ("串话"), so skip them. Key =
   `SHA-256(version + scope + model + normalizedInput)`, truncated. The version constant in
   the key means bumping it invalidates everything at once when prompt/output-shape changes.

3. **Redis backend with auto-degrade to in-process LRU.** Configure via `REDIS_URL`. If
   unset OR connect/ping fails OR a runtime op throws → fall back to an in-process LRU
   (Map-based, TTL + size eviction). This keeps "clone-and-run with zero external deps"
   working (the same principle behind the project's mock mode).

## Normalization (raises hit rate)
Fold semantically-equivalent inputs to one key: `trim` → lowercase → full-width space
`\u3000`→ space → collapse runs of whitespace → strip trailing CN/EN punctuation
(`!！?？。.,，、;；:：~～-_/\`). So "注册", "注册 ", "注册！" all map to the same key.

## Key shape
```
a2ui:cache:<version>:<scope>:<sha256(JSON{v,s,m,i}).slice(0,32)>
```
Include model id in the hash material — different models must not share cached answers.

## Implementation notes that bit during the build
- **Dynamic-import the Redis client** (`const { default: Redis } = await import('ioredis')`)
  inside the factory, not a top-level import, so no-Redis environments don't pay load/bundle
  cost. Construct with `{ lazyConnect: true, maxRetriesPerRequest: 1, retryStrategy: () => null }`
  then `await client.connect(); await client.ping()` — without `retryStrategy: () => null`
  ioredis spams reconnect logs forever when Redis is down.
- Type the Redis client as `any` in the wrapper to dodge type friction during `ng build`.
- Cache the store as a module-level singleton (`let _store`); expose a
  `_resetCacheStoreForTest()` for tests.
- **Mock-mode parity:** if the project has a mock flow (`flows.mock.ts`), wire the SAME
  template layer into it so mock and real behavior match. Mock needs only the template
  layer, not Redis/cache.
- Add the Redis client to `angular.json` `allowedCommonJsDependencies` to silence the
  CommonJS optimization-bailout warning (ioredis + redis-parser + debug are CJS). Build
  still succeeds without this — it's just a warning.

## Safety boundary (state it, enforce it)
- Multi-turn requests never enter the generic cache → no cross-session contamination.
- Templates return UI skeletons only; PII / session tokens never written to any shared cache.

## Verifying without a server
Fastest確定性 check is a tiny `tsx` script importing `cache.ts`/`templates.ts` directly,
asserting: normalization folding, same-input/same-model → same key, different-model →
different key, template hit returns the form spec + options, non-matching input returns
null, LRU set/get round-trip + miss→null. Then one end-to-end probe through the mock SSR
(Python urllib with UTF-8 to avoid git-bash curl mojibake) confirming a "register" request
returns the form and a normal request bypasses the template.

PITFALL: write the test `.mjs` INSIDE the project dir, not `/tmp`. Under MSYS, `/tmp`
resolves to `C:\Users\...\Temp`, so relative imports like `./src/cache.ts` resolve against
Temp and fail with ERR_MODULE_NOT_FOUND.
