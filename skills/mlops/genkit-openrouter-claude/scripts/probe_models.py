#!/usr/bin/env python3
"""Probe OpenRouter model availability for the current key + region.

Lists matching models, then sends a tiny request to each to see whether it's
region-blocked (403) and which upstream provider it routes to. Uses urllib only
(no deps). Reads the API key from a .env file or the OPENROUTER_API_KEY env var.

Usage:
    python probe_models.py                 # default filter: "claude"
    python probe_models.py opus            # filter substring
    python probe_models.py ""              # all models (can be a lot)

Env:
    OPENROUTER_API_KEY   API key (overrides .env)
    ENV_FILE             path to .env (default: ./.env)

NOTE: this script does NOT use a proxy. Run it from a shell whose egress already
reaches an allowed region (e.g. via Clash). Its purpose is to confirm model ids
and region availability, not to mirror Node's (proxy-less) fetch behavior.
"""
import json
import os
import sys
import urllib.request
import urllib.error

API = "https://openrouter.ai/api/v1"


def load_key():
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if k:
        return k
    env_file = os.environ.get("ENV_FILE", ".env")
    try:
        with open(os.path.expanduser(env_file), encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("OPENROUTER_API_KEY"):
                    return s.split("=", 1)[1].strip().strip('"').strip()
    except FileNotFoundError:
        pass
    sys.exit("No API key: set OPENROUTER_API_KEY or put it in .env")


def list_models(substr):
    req = urllib.request.Request(API + "/models")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    ids = [m["id"] for m in data.get("data", [])]
    if substr:
        ids = [i for i in ids if substr.lower() in i.lower()]
    return sorted(ids)


def test(model, key, retries=4):
    payload = {
        "model": model,
        "max_tokens": 8,
        "messages": [{"role": "user", "content": "hi"}],
    }
    body = json.dumps(payload).encode()
    hdr = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    for _ in range(retries):
        try:
            rq = urllib.request.Request(API + "/chat/completions", data=body, headers=hdr)
            with urllib.request.urlopen(rq, timeout=40) as r:
                d = json.load(r)
                return f"OK [{d.get('provider', '?')}]"
        except urllib.error.HTTPError as e:
            try:
                msg = str(json.load(e).get("error", {}).get("message", "?"))[:60]
            except Exception:
                msg = "?"
            return f"ERR {e.code} -> {msg}"
        except Exception:
            continue  # transient (SSL EOF etc.) -> retry
    return "NET-FAIL after retries"


def main():
    substr = sys.argv[1] if len(sys.argv) > 1 else "claude"
    key = load_key()
    ids = list_models(substr)
    print(f"=== models matching {substr!r} ({len(ids)}) ===")
    for m in ids:
        print("  ", m)
    print("\n=== region availability ===")
    for m in ids:
        print(f"  {m}: {test(m, key)}")


if __name__ == "__main__":
    main()
