#!/usr/bin/env bash
# Diagnose OpenRouter "This model is not available in your region." 403s.
# Distinguishes the three independent causes documented in SKILL.md:
#   (1) Node fetch ignoring the system proxy (exit-IP mismatch) — the big one
#   (2) a specific model id being region-blocked while a newer one works
#   (3) (only relevant once 1+2 are ruled out) genuine account/region block
#
# Usage: OPENROUTER_API_KEY=sk-or-... bash diagnose-region-403.sh
# Optional: HTTPS_PROXY must already be set in env if you use a proxy (Clash etc.)
set -u
KEY="${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}"

echo "=== proxy env ==="
env | grep -i proxy || echo "(no proxy env vars set)"

echo; echo "=== exit IP comparison (THE key signal) ==="
echo -n "curl   : "; curl -s --max-time 15 https://api.ipify.org; echo
echo -n "python : "; python -c "import urllib.request;print(urllib.request.urlopen('https://api.ipify.org',timeout=15).read().decode())" 2>&1
echo -n "node(direct) : "; node -e "fetch('https://api.ipify.org').then(r=>r.text()).then(t=>console.log(t)).catch(e=>console.log('ERR',e.message))"
# If curl/python show an ALLOWED ip but node errors or shows a DIFFERENT ip,
# the cause is Node fetch not using the proxy → fix with undici ProxyAgent (see SKILL.md).

echo; echo "=== node fetch THROUGH proxy (needs: npm i undici) ==="
node -e "
const p = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (!p) { console.log('no proxy env; skipping'); process.exit(0); }
try { const {ProxyAgent}=require('undici');
  fetch('https://api.ipify.org',{dispatcher:new ProxyAgent(p)})
    .then(r=>r.text()).then(t=>console.log('node-via-proxy exit IP:',t))
    .catch(e=>console.log('ERR',e.message));
} catch(e){ console.log('install undici first: npm i undici'); }
"

echo; echo "=== which Claude model ids actually answer (direct curl, bypasses Node) ==="
for M in anthropic/claude-sonnet-4 anthropic/claude-sonnet-4.5 anthropic/claude-3.5-haiku; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
    https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
    -d "{\"model\":\"$M\",\"max_tokens\":8,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}]}")
  echo "  $M -> HTTP $code"
done
echo "(200 = usable; 403 = region-blocked for that id; try a newer id)"
