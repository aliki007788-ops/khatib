"""مانیتورینگ ساده + ثبت خطا"""
from __future__ import annotations
import os, time, traceback, json
from collections import deque
from threading import Lock

_lock = Lock()
_errors: deque = deque(maxlen=200)
_counters = {"requests": 0, "errors": 0, "speeches": 0, "payments": 0}
STARTED = time.time()

def inc(name: str, n: int = 1):
    with _lock:
        _counters[name] = _counters.get(name, 0) + n

def log_error(where: str, err: Exception | str, detail: str = ""):
    with _lock:
        _counters["errors"] = _counters.get("errors", 0) + 1
        _errors.appendleft({
            "ts": time.time(),
            "where": where,
            "error": str(err)[:300],
            "detail": detail[:500],
        })
    # Sentry-like hook
    webhook = os.getenv("ERROR_WEBHOOK_URL", "")
    if webhook:
        try:
            import httpx
            httpx.post(webhook, json={"where": where, "error": str(err)[:300]}, timeout=3)
        except Exception:
            pass

def snapshot() -> dict:
    with _lock:
        return {
            "uptime_sec": int(time.time() - STARTED),
            "counters": dict(_counters),
            "recent_errors": list(_errors)[:20],
        }
