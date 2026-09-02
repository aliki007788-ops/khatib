#!/usr/bin/env python3
"""تست دود End-to-End — python scripts/e2e_smoke.py [BASE_URL]"""
import sys, uuid
import urllib.request, urllib.parse, json, http.cookiejar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

def req(path, data=None, method=None):
    url = BASE + path
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        r = urllib.request.Request(url, data=body, method=method or "POST")
        r.add_header("Content-Type", "application/x-www-form-urlencoded")
    else:
        r = urllib.request.Request(url, method=method or "GET")
    with opener.open(r, timeout=30) as resp:
        return json.loads(resp.read().decode())

def main():
    errors = []
    try:
        h = req("/health")
        assert h.get("status") == "ok", h
        print("OK health", h.get("version"))
    except Exception as e:
        errors.append(f"health: {e}")
        print("FAIL health", e)
        return 1

    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    try:
        reg = req("/api/register", {"email": email, "password": "testpass12", "name": "Test"})
        assert reg.get("ok"), reg
        print("OK register")
    except Exception as e:
        errors.append(f"register: {e}")
        print("FAIL register", e)

    try:
        me = req("/api/me")
        assert me.get("logged"), me
        print("OK me")
    except Exception as e:
        errors.append(f"me: {e}")

    try:
        sp = req("/api/speech", {"topic": "تست", "text": "سلام. امروز می‌خواهم سه نکته درباره اعتماد به نفس بگویم. اول تمرین. دوم بازخورد. سوم تکرار."})
        assert "score" in sp, sp
        print("OK speech score=", sp.get("score"))
    except Exception as e:
        errors.append(f"speech: {e}")
        print("FAIL speech", e)

    try:
        sub = req("/api/subscription")
        assert "plan" in sub, sub
        print("OK subscription", sub.get("plan"))
    except Exception as e:
        errors.append(f"subscription: {e}")

    try:
        m = req("/metrics")
        print("OK metrics", m.get("counters"))
    except Exception as e:
        errors.append(f"metrics: {e}")

    if errors:
        print("FAILED", len(errors))
        return 1
    print("ALL SMOKE TESTS PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
