#!/usr/bin/env bash
# Pre-commit secret-safety gate for a Hermes sync repo.
# Run from the Hermes home dir AFTER writing .gitignore and `git init`.
# Stages everything, then asserts: zero danger files + zero key-shaped content.
# Exit 0 = safe to commit/push. Non-zero = STOP, a secret would leak.
set -u
cd "$(git rev-parse --show-toplevel)" || exit 2

# refresh staging so .gitignore is honored (drops nothing already tracked — see note)
git rm -r --cached -q . >/dev/null 2>&1
git add -A

echo "=== staged file count ==="
git diff --cached --name-only | wc -l

echo ""
echo "=== top-level (non-skills) staged — should be only safe items ==="
git diff --cached --name-only | grep -vE '^skills/' || true

echo ""
echo "=== DANGER FILE scan (must be empty) ==="
danger=$(git diff --cached --name-only | grep -iE \
  '(\.env|auth\.json|^config\.yaml|state\.db|\.bak|^weixin|^whatsapp|^pairing|node_modules|config\.json$|kanban\.db|response_store|\.lock$|_route)')
if [ -n "$danger" ]; then
  echo "$danger"
  echo "FAIL: danger files staged"; exit 1
fi
echo "OK: no danger files"

echo ""
echo "=== CONTENT key scan (real keys only; placeholders allowed) ==="
hits=$(git diff --cached | grep -inE \
  '(sk-[a-zA-Z0-9]{20}|AKID[A-Za-z0-9]{10}|AIza[A-Za-z0-9]{30}|ghp_[A-Za-z0-9]{20}|xox[baprs]-|-----BEGIN.*PRIVATE KEY|webServiceKey["'"'"']?\s*:\s*["'"'"'][a-f0-9]{20})' \
  | grep -vEi '(example|placeholder|YOUR_|<your|xx\.\.\.xx|占位|description)')
if [ -n "$hits" ]; then
  echo "$hits"
  echo "FAIL: key-shaped content staged — inspect each before proceeding"; exit 1
fi
echo "OK: no real key strings"
echo ""
echo "SAFE TO COMMIT/PUSH"
