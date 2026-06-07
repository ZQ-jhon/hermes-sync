# iCloud CalDAV 401 Unauthorized — ordered troubleshooting

A 401 from `caldav.icloud.com` is almost never a code/library/protocol bug. The
response headers tell you the account is real and Basic auth is accepted:

```
HTTPError 401
WWW-Authenticate: Basic realm="MMCalDav"
WWW-Authenticate: X-MobileMe-AuthToken realm="MMCalDav"
x-apple-user-partition: 25        <- server FOUND the account's data partition
Server: AppleHttpServer/...
```

`x-apple-user-partition` being present means **Apple located the account**. So the
401 is "this username+password pair is rejected," not "no such account." Work the
list below top to bottom; stop at the first that applies.

## 1. iCloud Calendar service not enabled (MOST COMMON, silent)
The user can have a valid Apple ID, 2FA on, and a perfect App-Specific Password,
and still get 401 if the **Calendar** service was never turned on for iCloud.
- iPhone: Settings → [name] → iCloud → toggle **Calendar** ON.
- Web: can they open the **Calendar** app at icloud.com? If not, it's not enabled.
- After enabling, Apple's backend takes a few minutes to sync to the CalDAV
  endpoint. Wait, then retry. (In this session the user enabled it mid-debug; the
  first retries still 401'd because of cause #3 below.)

## 2. Advanced Data Protection (高级数据保护) is ON
If ADP is enabled, third-party CalDAV / Basic access is blocked ENTIRELY. No
password will ever work. Check: iPhone Settings → [name] → iCloud → Advanced Data
Protection, or account.apple.com → Sign-In & Security. Must be OFF for CalDAV.

## 3. Password was generated on a DIFFERENT Apple ID than the calendar's
Users frequently have multiple Apple IDs. The one they log into account.apple.com
with (and generate App-Specific Passwords on) may not be the one their calendar
lives on. Confirm the calendar's owning account on iPhone:
Settings → [name] → iCloud → Calendar — note which Apple ID that is, and generate
the App-Specific Password on THAT account.
- Symptom that points here: TWO freshly-generated passwords both 401, while
  Calendar is confirmed ON and ADP confirmed OFF. Timing/sync is no longer a
  plausible explanation — suspect account identity.

## 4. Stale App-Specific Password
Apple invalidates these on page refresh or after a delay. Regenerate, copy the
`xxxx-xxxx-xxxx-xxxx` string IMMEDIATELY, and use it WITHOUT refreshing the page.

## Things that are NOT the cause (don't waste time)
- The operating system (Windows/Linux/Mac all behave identically).
- The HTTP library or HTTP/2 vs HTTP/1.1 (server accepts both).
- Email-vs-username format (`appleid@gmail.com` is the correct username form).
- The `partition=NN` number changing between attempts (load-balancer noise).

## Endpoints to probe
- `https://caldav.icloud.com` — international accounts.
- `https://caldav.icloud.com.cn` — China-region (云上贵州) accounts. If `.com`
  401s and the user is in China, try this. (In this session `.cn` also 401'd, so
  region was not the cause — but rule it out cheaply.)
- `https://pNN-caldav.icloud.com` — partition host (NN from the partition header).
  Rarely required; cheap to try.

Use `scripts/diag_icloud_caldav.py` to run all of these in one shot.
