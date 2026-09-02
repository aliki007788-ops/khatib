#!/usr/bin/env python3
"""Worker مستقل Redis برای پردازش صوت — اجرا: python worker.py"""
import os, sys, time, asyncio, json

# ensure app import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.queue import pop_job, get_job, set_job, queue_enabled
from app.core.db import SessionLocal, init_db
from app.core.models import Speech, AuditLog, User
from app.core.plans import consume_usage
from app.services.ai import transcribe, generate_coaching_feedback
from app.services.audio_dsp import analyze_audio_file
import re

async def process_one(job_id: str):
    job = get_job(job_id)
    if not job:
        return
    set_job(job_id, status="running")
    payload = job.get("payload") or {}
    user_id = payload.get("user_id")
    topic = payload.get("topic", "تمرین صوتی")
    path = payload.get("path")
    est_sec = int(payload.get("est_sec") or 30)
    db = SessionLocal()
    try:
        text = await transcribe(path)
        analysis = await generate_coaching_feedback(text, topic)
        dsp = analyze_audio_file(path, fallback_duration_sec=est_sec)
        words = re.findall(r"[\wآ-ی]+", text or "")
        fillers = ["یعنی", "مثلاً", "مثلا", "در واقع", "حالا", "خب"]
        analysis["dsp"] = dsp
        analysis["prosody"] = {
            "words": len(words),
            "filler_count": sum(1 for w in words if w in fillers),
            "duration_sec": dsp.get("duration_sec") or est_sec,
            "energy_level": dsp.get("energy_level"),
            "pitch_hz": dsp.get("pitch_hz"),
            "silence_ratio": dsp.get("silence_ratio"),
            "wpm": round(len(words) / max(int(dsp.get("duration_sec") or est_sec), 1) * 60, 1),
        }
        for n in dsp.get("notes") or []:
            analysis.setdefault("weaknesses", [])
            if n not in analysis["weaknesses"]:
                analysis["weaknesses"].append(n)
        u = db.get(User, user_id)
        if u:
            consume_usage(u, int(dsp.get("duration_sec") or est_sec))
        s = Speech(
            user_id=user_id, topic=topic, text=text,
            score=analysis.get("score", 0),
            analysis=json.dumps(analysis, ensure_ascii=False),
            audio_path=path,
            duration_sec=int(dsp.get("duration_sec") or est_sec),
        )
        db.add(s)
        db.add(AuditLog(user_id=user_id, action="speech_worker", detail=topic))
        db.commit()
        db.refresh(s)
        set_job(job_id, status="done", result={"id": s.id, **analysis})
        print(f"[worker] done {job_id} speech={s.id}")
    except Exception as e:
        set_job(job_id, status="error", error=str(e)[:400])
        print(f"[worker] error {job_id}: {e}")
    finally:
        db.close()

def main():
    if not queue_enabled():
        print("REDIS_URL تنظیم نشده — worker خارج می‌شود.")
        sys.exit(1)
    init_db()
    print("Khatib worker started. Waiting for jobs...")
    while True:
        jid = pop_job(timeout=5)
        if jid:
            asyncio.run(process_one(jid))
        else:
            time.sleep(0.2)

if __name__ == "__main__":
    main()
