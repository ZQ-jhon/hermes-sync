---
name: icloud-caldav
description: Connect to Apple Calendar / iCloud (read+write+sync) over CalDAV from any host (Windows/Linux/Mac), using the Python `caldav` library + an App-Specific Password. Use when a user asks to connect, read, create, or sync Apple/iCloud calendar events. Includes a full 401-Unauthorized troubleshooting decision tree.
---

# iCloud CalDAV (Apple Calendar)

There is NO one-click Apple Calendar connector and no Apple Calendar app on Windows/Linux. The only viable path to read/write/sync an Apple/iCloud calendar from a non-Apple host is **iCloud CalDAV**: the Python `caldav` library authenticating to `https://caldav.icloud.com` with the user's **Apple ID + an App-Specific Password** (NOT the main Apple password).

The OS does NOT matter. CalDAV is plain HTTPS — it behaves identically on Windows, Linux, and macOS. If a connection fails, the cause is authentication/account state, never "because it's Windows." Do not tell the user Windows is the problem.

## What the user must do first (you cannot do this for them)
1. Apple ID must have **two-factor authentication (2FA)** enabled (required for App-Specific Passwords to exist).
2. **iCloud Calendar service must be turned ON** for the account (iPhone: Settings → name → iCloud → Calendar toggle; or check calendar loads at icloud.com). If it was never enabled, CalDAV returns 401 even with a perfect password. This is the single most common silent blocker.
3. Generate an **App-Specific Password** at https://account.apple.com → 登录和安全 / Sign-In & Security → App-Specific Passwords → generate. Copy it IMMEDIATELY (format `xxxx-xxxx-xxxx-xxxx`) and send it without refreshing the page — Apple invalidates it on refresh/timeout.

## Connecting (known-good)
```python
from caldav import DAVClient
client = DAVClient(url="https://caldav.icloud.com",
                   username="appleid@example.com",
                   password="xxxx-xxxx-xxxx-xxxx")
cals = client.principal().calendars()
for c in cals:
    print(c.get_display_name(), c.url)
```
Install: `pip install caldav icalendar`.

## 401 Unauthorized — DON'T thrash, follow the decision tree
A 401 with `WWW-Authenticate: Basic realm="MMCalDav"` and an `x-apple-user-partition: NN` header means **the server recognizes the account and accepts Basic auth, but rejects this username+password pair**. The library/protocol/host is fine — the problem is credentials or account state. See `references/troubleshooting-401.md` for the ordered checklist. Run `scripts/diag_icloud_caldav.py` to probe quickly without spamning manual attempts.

The two causes that actually matter, in order:
1. **iCloud Calendar service not enabled** (user thinks the account is set up but never toggled Calendar on). Fix: enable it, wait a few minutes for Apple backend sync, retry.
2. **App-Specific Password is stale/invalid** — Apple invalidates these on page refresh or after time. A brand-new password that still 401s usually means cause #1, OR the password was generated on a DIFFERENT Apple ID than the one the calendar lives on (users often have multiple Apple IDs). Have them confirm on iPhone: Settings → name → iCloud → Calendar shows which account owns the calendar.

Do NOT keep retrying the same dead password expecting Apple sync to fix it — if two freshly-generated passwords both 401 and Calendar is confirmed ON + Advanced Data Protection OFF, the account identity is the suspect, not timing.

## Pitfalls
- **Don't blame the OS.** Windows is irrelevant; the failure is always auth/account state.
- **Advanced Data Protection (高级数据保护)**: if ON, third-party CalDAV/Basic access is blocked entirely — no password will ever work. Confirm it's OFF before deep debugging.
- **China-region Apple IDs** live at `caldav.icloud.com.cn`, not `.com`. Worth a probe if `.com` 401s. (In this session the `.cn` endpoint also 401'd, so region was not the cause — but always rule it out.)
- **Partition host**: some accounts route via `pNN-caldav.icloud.com` (NN from the `x-apple-user-partition` header). Rarely required, but cheap to probe.
- **Never persist the App-Specific Password** in code or committed files — pass via env var. After setup, advise the user to revoke any password they pasted into chat and regenerate.
- The `partition=NN` number changing across attempts is just load-balancer routing noise — NOT a diagnostic signal.

## After connecting
Wrap into: list calendars, read events (date range), create/update/delete events (icalendar VEVENT). For "daily agenda to WeChat/Telegram" style sync, build a cron job that reads today's events and pushes a digest.
