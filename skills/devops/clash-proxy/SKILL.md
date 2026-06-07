---
name: clash-proxy
description: Control Clash for Windows proxy — find API port, authenticate, switch nodes, diagnose TLS issues. Use when proxy isn't working, need to switch exit node, or debug HTTP 403 / TLS reset through proxy.
---

# Clash Proxy Control

Triggers: proxy not working, need to switch Clash node, 403 region errors, TLS reset through proxy, "梯子" issues, OpenRouter region blocking.

## Finding the API Port

CFW has `randomControllerPort: true` by default. The API port changes every restart.

**Discovery:**

```bash
# Find clash-win64.exe PID, then its listening ports
# On Windows (git-bash):
netstat -ano | grep clash-win64 | grep LISTENING
# → 127.0.0.1:7890   (proxy)
# → 127.0.0.1:54532  (API — the non-7890 one)
```

Or read from `D:\clash\Clash\Data\config.yaml`:
```yaml
mixed-port: 7890
external-controller: 127.0.0.1:54532
secret: 409773e3-67f4-455f-aa58-5183ccd9eee4
```

## Authentication

CFW uses **URL query parameter** `?token=<secret>`, NOT `Authorization: Bearer` header:

```bash
# ✅ Works
curl "http://127.0.0.1:54532/proxies?token=<secret>"

# ❌ Does NOT work
curl -H "Authorization: Bearer <secret>" http://127.0.0.1:54532/proxies
```

## Switching Nodes

```bash
# Change GLOBAL proxy node
curl -X PUT "http://127.0.0.1:54532/proxies/GLOBAL?token=<secret>" \
  -H 'Content-Type: application/json' \
  -d '{"name":"🇺🇸 美国 B"}'
```

To get available nodes:
```bash
curl "http://127.0.0.1:54532/proxies?token=<secret>" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
for k,v in d['proxies'].items():
    if v.get('type')=='Selector':
        print(f\"{k}: {v['now']}\")
        for n in v['all']: print(f'  - {n}')
"
```

## Git Push Through Proxy

Git on Windows may use `schannel` SSL backend, which can cause TLS resets through proxy. Per-command proxy flags (NEVER `--global`):

```bash
git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push
```

If TLS is reset: the current node may be blocked by the target (e.g. GitHub blocks some IP ranges). Switch to a different node (see above).

### SSH Fallback When HTTPS Proxy TLS Fails

When `git -c http.proxy=... push` gets TLS reset even after switching nodes, use SSH through the proxy:

```bash
# Verify SSH tunnel works (requires `connect` — included with git-bash on Windows)
ssh -o "ProxyCommand=connect -H 127.0.0.1:7890 %h %p" -T git@github.com
# Expected: "Permission denied (publickey)" — tunnel works, just need key registered

# Switch remote to SSH and push
git remote set-url origin git@github.com:user/repo.git
git -c core.gitProxy='"connect -H 127.0.0.1:7890 %h %p"' push origin main
```

**Pitfall:** If the SSH key (`~/.ssh/id_ed25519.pub`) is not registered on GitHub, this fails with "Permission denied (publickey)". Register the key at https://github.com/settings/keys or revert to HTTPS and fix the node issue. After SSH push, remember to restore the HTTPS remote if that's the project's default.

## Python API Calls (Windows)

`execute_code` cannot make network requests. Use a Python script run via `terminal`:

```python
import urllib.request, json
secret = "..."
base = "http://127.0.0.1:54532"
def clash(path, method="GET", body=None):
    url = f"{base}{path}?token={secret}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())
```

## Key Files

- Config: `D:\clash\Clash\Data\config.yaml`
- Settings: `D:\clash\Clash\Data\cfw-settings.yaml`
- Profiles: `D:\clash\Clash\Data\profiles\`
