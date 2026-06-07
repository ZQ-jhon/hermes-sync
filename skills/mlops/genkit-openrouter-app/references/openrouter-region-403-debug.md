# Debug transcript: OpenRouter region-403 with Genkit was a Node-proxy problem

A long, instructive debugging session. The error `403 This model is not available
in your region.` is highly misleading — it points at model/region/key, but the real
cause was transport. Recorded so a future session can short-circuit the elimination.

## The contradiction that cracked it
- `curl` and Python (urllib) to `https://openrouter.ai/api/v1/chat/completions` with the
  exact same body + key → **200 OK**, repeatedly.
- Genkit (`@genkit-ai/compat-oai` → openai SDK → Node built-in `fetch`) with a byte-identical
  body/URL/method → **403** every time.

## Hypotheses eliminated (each was a dead end)
1. **Wrong model id** — partly real: `anthropic/claude-sonnet-4` (old) was region-blocked,
   but `claude-sonnet-4.5` was fine. Not the whole story; Genkit still 403'd on 4.5.
2. **`provider` routing not transmitted** — verified via a logging `fetch` that the body
   DID contain `provider:{order:['Amazon Bedrock'],allow_fallbacks:false}`. Transmitted, still 403.
   (Confirmed mechanism: compat-oai validates config against the Zod schema and drops unknown
   keys; a `.passthrough()` configSchema lets them through — but that wasn't the bug here.)
3. **User-Agent / `x-stainless-*` headers** — openai SDK adds `user-agent: OpenAI/JS 4.104.0`.
   Replayed those exact headers from Python → still 200. Not the cause.
4. **Streaming / response_format** — Python with `stream:true` and with
   `response_format: json_schema` → both 200. Not the cause.
5. **URL/path/body** — logging fetch showed identical URL+body to the curl that succeeded.

## The actual signal
Compared exit IPs:
- `curl https://api.ipify.org` → `23.247.137.157` (an OpenRouter-ALLOWED region)
- Python → same allowed IP
- `node -e "fetch('https://api.ipify.org')..."` → **`fetch failed`** / went direct

Machine had `HTTPS_PROXY=http://127.0.0.1:7890` (Clash). curl/Python honor it; **Node's
built-in fetch/undici does NOT read HTTP(S)_PROXY env vars** and connected directly, landing
on a blocked exit IP → 403.

## Proof of fix
```
node -e "const {ProxyAgent}=require('undici');
  fetch('https://api.ipify.org',{dispatcher:new ProxyAgent('http://127.0.0.1:7890')})
    .then(r=>r.text()).then(t=>console.log(t))"
# => 23.247.137.157   (now the allowed IP)
```
Wiring that proxy-aware fetch into `openAICompatible({ fetch })` → Genkit returned the full
structured recipe. `npx tsc --noEmit` exit 0.

## Lesson / fast path next time
When a Node HTTP client 403s with a region message but curl/Python succeed on the SAME
request: **compare exit IPs first.** A mismatch means the Node client isn't using the proxy
your shell tools use. Fix = undici `ProxyAgent` injected as the client's `fetch`/dispatcher.
This applies to ANY Node SDK on built-in fetch (openai, anthropic, etc.), not just Genkit.
Run scripts/diagnose-region-403.sh to do this comparison automatically.
