---
name: postman-collections
description: Author Postman collections/environments as importable v2.1 JSON, organize workspace folders, and push to a workspace via the Postman API. Use when asked to add endpoints, folders, environment variables/secrets, or test scripts to Postman.
---

# Postman Collections & Environments

Create and populate Postman workspaces by generating standard **importable JSON**, or by calling the **Postman API** for direct writes. Covers folders, endpoints, environment/collection variables (incl. secrets), and auto-token test scripts.

## Critical constraint — DO NOT edit the desktop app's local store
- Postman desktop keeps collections/environments in an **IndexedDB leveldb** store (binary) under `AppData\Roaming\Postman\Partitions\<id>\IndexedDB\...`. **Editing it by hand corrupts the DB.** Never write there.
- The agent **cannot drive the Postman GUI** (clicking "New Folder" etc.). So there are exactly two safe ways to add content:
  1. **Generate importable JSON** (collection v2.1 + environment) → user does `Import` in Postman. Cleanest, no credentials needed. **Default to this.**
  2. **Postman API** — needs the user's API key + workspace ID. Fully automatable. Use only when the user provides a key.

## Workflow (default: JSON import)
1. **Gather specifics first — do not invent.** Ask the user for:
   - Folder/directory name(s) (e.g. `Auth`, `Users`, `Orders`).
   - Endpoints: method + path, e.g. `POST {{base_url}}/login`, `GET {{base_url}}/users/:id`.
   - Variables: plain (`base_url`) and secrets (`api_key`, `auth_token` — put placeholders, user fills real values).
   - Whether to include a login→token auto-save test script.
   If they have no list, offer a **standard best-practice skeleton** (Auth folder, login endpoint, token auto-injection, dev/prod env templates) for them to edit.
2. Build collection JSON from `templates/collection-v2.1.json` and an environment JSON from `templates/environment.json`.
3. Reference variables with `{{var}}`; path params as `:param` in URL + a `variable` entry.
4. Validate JSON parses, hand the file path to the user to Import.

## Best-practice conventions (from common Postman guidance)
- Use **environments** to switch dev/test/prod; reference everything via `{{base_url}}`, `{{api_key}}`.
- Variable scope precedence: local > data > environment > collection > global.
- Mark secrets as `type: "secret"` in environment values so they're masked.
- Chain requests: in a login request's **Tests** tab, extract the token and `pm.environment.set("auth_token", json.token)`; downstream requests send `Authorization: Bearer {{auth_token}}`.

## Postman API path (when user gives an API key)
- Auth header: `X-Api-Key: <key>`.
- Create collection: `POST https://api.getpostman.com/collections?workspace=<workspaceId>` with `{"collection": {...v2.1...}}`.
- Create environment: `POST https://api.getpostman.com/environments?workspace=<workspaceId>`.
- List workspaces to find the ID: `GET https://api.getpostman.com/workspaces`.
- **Verify** after POST: re-GET the returned uid and confirm it exists before reporting success.

## Pitfalls
- Don't claim a workspace was modified unless you imported JSON yourself or got a verified API response — the agent can't see the user's GUI state.
- A "workspace" (e.g. "B-FE") is a container; the user imports into it or you target it via `?workspace=<id>`.
- Token/key values: never hardcode real secrets into committed JSON; use placeholders or env vars.

## Files
- `templates/collection-v2.1.json` — minimal valid collection skeleton with an Auth folder, a login request (with token-save test), and a `{{base_url}}` variable.
- `templates/environment.json` — dev environment with a plain var and a secret var.