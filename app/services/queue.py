"""صف پردازش صوت با Redis — اگر REDIS_URL نباشد، همگام اجرا می‌شود."""
from __future__ import annotations
import os
import json
import uuid
import time
from typing import Any, Callable

REDIS_URL = os.getenv("REDIS_URL", "")

_memory_jobs: dict[str, dict] = {}

def _redis():
    if not REDIS_URL:
        return None
    try:
        import redis
        return redis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        return None

def enqueue(job_type: str, payload: dict) -> str:
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "type": job_type,
        "payload": payload,
        "status": "queued",
        "result": None,
        "error": None,
        "created": time.time(),
    }
    r = _redis()
    if r:
        r.hset(f"khatib:job:{job_id}", mapping={
            "data": json.dumps(job, ensure_ascii=False),
            "status": "queued",
        })
        r.lpush("khatib:queue", job_id)
        r.expire(f"khatib:job:{job_id}", 86400)
    else:
        _memory_jobs[job_id] = job
    return job_id

def set_job(job_id: str, **fields):
    r = _redis()
    if r:
        raw = r.hget(f"khatib:job:{job_id}", "data")
        job = json.loads(raw) if raw else {"id": job_id}
        job.update(fields)
        r.hset(f"khatib:job:{job_id}", mapping={
            "data": json.dumps(job, ensure_ascii=False),
            "status": job.get("status", "unknown"),
        })
    elif job_id in _memory_jobs:
        _memory_jobs[job_id].update(fields)

def get_job(job_id: str) -> dict | None:
    r = _redis()
    if r:
        raw = r.hget(f"khatib:job:{job_id}", "data")
        return json.loads(raw) if raw else None
    return _memory_jobs.get(job_id)

def pop_job(timeout: int = 2) -> str | None:
    r = _redis()
    if r:
        item = r.brpop("khatib:queue", timeout=timeout)
        if item:
            return item[1]
        return None
    # memory: first queued
    for jid, job in list(_memory_jobs.items()):
        if job.get("status") == "queued":
            job["status"] = "running"
            return jid
    return None

def queue_enabled() -> bool:
    return bool(REDIS_URL)
