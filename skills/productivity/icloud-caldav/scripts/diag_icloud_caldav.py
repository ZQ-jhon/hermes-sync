#!/usr/bin/env python3
"""iCloud CalDAV connection diagnostic probe.

Probes the iCloud CalDAV endpoints with a single Apple ID + App-Specific Password
and prints the HTTP status + key headers, so you can distinguish "account/password
rejected" (401) from "endpoint wrong" (URLError) without thrashing manual attempts.

Usage:
    ICLOUD_USER='appleid@example.com' ICLOUD_PASS='xxxx-xxxx-xxxx-xxxx' \
        python diag_icloud_caldav.py

Never hardcode the password — pass it via env var.
A 401 with x-apple-user-partition header set => account recognized, credentials
rejected => see references/troubleshooting-401.md (usually: Calendar service not
enabled, stale password, or wrong Apple ID).
"""
import os, sys, base64, urllib.request, ssl

user = os.environ.get("ICLOUD_USER")
pw = os.environ.get("ICLOUD_PASS")
if not user or not pw:
    print("Set ICLOUD_USER and ICLOUD_PASS env vars.")
    sys.exit(1)

BODY = '<?xml version="1.0"?><propfind xmlns="DAV:"><prop><current-user-principal/></prop></propfind>'
AUTH = base64.b64encode(f"{user}:{pw}".encode()).decode()

# .com (international), .com.cn (China region), and partition hosts are all worth probing.
HOSTS = [
    "caldav.icloud.com",
    "caldav.icloud.com.cn",
]

def probe(host):
    req = urllib.request.Request(f"https://{host}/", data=BODY.encode(), method="PROPFIND")
    req.add_header("Authorization", "Basic " + AUTH)
    req.add_header("Depth", "0")
    req.add_header("Content-Type", "application/xml; charset=utf-8")
    req.add_header("User-Agent", "macOS/13.0 (22A380) CalendarAgent/940")
    try:
        resp = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=25)
        return resp.status, dict(resp.headers), resp.read()[:600].decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), ""
    except Exception as e:
        return f"EXC {type(e).__name__}", {}, str(e)[:150]

partition = None
for host in HOSTS:
    code, hdrs, txt = probe(host)
    part = hdrs.get("x-apple-user-partition", "-")
    if part != "-":
        partition = part
    print(f"{host:28s} -> {code}   partition={part}")
    if str(code).startswith("2"):
        print("  CONNECTED. principal XML:")
        print("  " + txt.replace("\n", "\n  "))
        sys.exit(0)

# If a partition was reported, try the partition-specific host once.
if partition and partition != "-":
    host = f"p{partition}-caldav.icloud.com"
    code, hdrs, txt = probe(host)
    print(f"{host:28s} -> {code}   partition={hdrs.get('x-apple-user-partition','-')}")
    if str(code).startswith("2"):
        print("  CONNECTED via partition host.")
        sys.exit(0)

print()
print("All 401 with a partition header => account recognized, credentials rejected.")
print("Checklist (see references/troubleshooting-401.md):")
print("  1. Is iCloud Calendar service ENABLED for this account? (most common blocker)")
print("  2. Is Advanced Data Protection OFF? (if ON, CalDAV is blocked entirely)")
print("  3. Is this the Apple ID the calendar actually lives on? (multiple-account trap)")
print("  4. Regenerate App-Specific Password, copy immediately, don't refresh the page.")
