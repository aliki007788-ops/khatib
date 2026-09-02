import os, json, uuid
from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..core.db import get_db, SessionLocal
from ..core.models import Speech, AuditLog
from ..core.plans import can_analyze, consume_usage, effective_plan
from ..core.security import validate_audio_upload
from .auth import current
from ..services.ai import transcribe, generate_coaching_feedback
from ..services.audio_dsp import analyze_audio_file
from ..services.queue import enqueue, get_job, queue_enabled, set_job

router = APIRouter()

async def _process_audio_job(job_id: str, user_id: int, topic: str, path: str, est_sec: int):
    db = SessionLocal()
    try:
        set_job(job_id, status="running")
        text = await transcribe(path)
        analysis = await generate_coaching_feedback(text, topic)
        dsp = analyze_audio_file(path, fallback_duration_sec=est_sec)
        analysis["dsp"] = dsp
        analysis["prosody"] = {
            "words": len((text or "").split()),
            "duration_sec": dsp.get("duration_sec") or est_sec,
            "energy_level": dsp.get("energy_level"),
            "pitch_hz": dsp.get("pitch_hz"),
            "silence_ratio": dsp.get("silence_ratio"),
            "filler_count": analysis.get("prosody", {}).get("filler_count") if isinstance(analysis.get("prosody"), dict) else None,
        }
        for n in dsp.get("notes") or []:
            analysis.setdefault("weaknesses", [])
            if n not in analysis["weaknesses"]:
                analysis["weaknesses"].append(n)

        from ..core.models import User as UserModel
        u = db.get(UserModel, user_id)
        if u:
            consume_usage(u, int(dsp.get("duration_sec") or est_sec))
        s = Speech(
            user_id=user_id,
            topic=topic,
            text=text,
            score=analysis.get("score", 0),
            analysis=json.dumps(analysis, ensure_ascii=False),
            audio_path=path,
            duration_sec=int(dsp.get("duration_sec") or est_sec),
        )
        db.add(s)
        db.add(AuditLog(user_id=user_id, action="speech_audio_job", detail=topic))
        db.commit()
        db.refresh(s)
        result = {"id": s.id, **analysis}
        set_job(job_id, status="done", result=result)
    except Exception as e:
        set_job(job_id, status="error", error=str(e)[:300])
    finally:
        db.close()

@router.post("/speech")
async def speech_text(
    request: Request,
    topic: str = Form("تمرین آزاد"),
    text: str = Form(""),
    db: Session = Depends(get_db),
):
    from ..services.ai import generate_coaching_feedback as gcf
    import re
    u = current(request, db)
    if not u:
        return JSONResponse({"error": "ابتدا وارد شوید"}, 401)
    ok, msg = can_analyze(u, 0)
    if not ok:
        return JSONResponse({"error": msg}, 402)

    analysis = await gcf(text, topic)
    words = re.findall(r"[\wآ-ی]+", text or "")
    fillers = ["یعنی", "مثلاً", "مثلا", "در واقع", "حالا", "خب"]
    filler_count = sum(1 for w in words if w in fillers)
    analysis["prosody"] = {
        "words": len(words),
        "sentences": max(1, len(re.findall(r"[.!؟?؛\n]", text or ""))),
        "filler_count": filler_count,
        "duration_sec": 0,
    }
    consume_usage(u, 0)
    s = Speech(
        user_id=u.id,
        topic=topic,
        text=text,
        score=analysis.get("score", 0),
        analysis=json.dumps(analysis, ensure_ascii=False),
        duration_sec=0,
    )
    db.add(s)
    db.add(AuditLog(user_id=u.id, action="speech_text", detail=topic))
    db.commit()
    db.refresh(s)
    return {**analysis, "id": s.id, "plan": effective_plan(u)}

@router.post("/speech/audio")
async def speech_audio(
    request: Request,
    background_tasks: BackgroundTasks,
    topic: str = Form("تمرین صوتی"),
    audio: UploadFile = File(...),
    async_mode: str = Form("0"),
    db: Session = Depends(get_db),
):
    u = current(request, db)
    if not u:
        return JSONResponse({"error": "ابتدا وارد شوید"}, 401)

    raw = await audio.read()
    validate_audio_upload(audio.filename, len(raw))
    # ذخیره موقت برای استخراج مدت دقیق
    root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    up = os.path.join(root, "uploads")
    os.makedirs(up, exist_ok=True)
    ext = os.path.splitext(audio.filename or ".webm")[1].lower() or ".webm"
    path = os.path.join(up, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    from ..services.audio_dsp import exact_duration_sec
    exact = exact_duration_sec(path)
    est_sec = int(exact) if exact else max(5, min(600, len(raw) // 2500))
    ok, msg = can_analyze(u, est_sec)
    if not ok:
        return JSONResponse({"error": msg}, 402)


    use_queue = async_mode == "1" or (queue_enabled() and os.getenv("SPEECH_ASYNC", "1") == "1")

    if use_queue and queue_enabled():
        job_id = enqueue("speech_audio", {"user_id": u.id, "topic": topic, "path": path, "est_sec": est_sec})
        background_tasks.add_task(_process_audio_job, job_id, u.id, topic, path, est_sec)
        return {"job_id": job_id, "status": "queued", "message": "در صف پردازش قرار گرفت"}

    # همگام
    text = await transcribe(path)
    analysis = await generate_coaching_feedback(text, topic)
    dsp = analyze_audio_file(path, fallback_duration_sec=est_sec)
    analysis["dsp"] = dsp
    import re
    words = re.findall(r"[\wآ-ی]+", text or "")
    fillers = ["یعنی", "مثلاً", "مثلا", "در واقع", "حالا", "خب"]
    analysis["prosody"] = {
        "words": len(words),
        "filler_count": sum(1 for w in words if w in fillers),
        "duration_sec": dsp.get("duration_sec") or est_sec,
        "energy_level": dsp.get("energy_level"),
        "pitch_hz": dsp.get("pitch_hz"),
        "silence_ratio": dsp.get("silence_ratio"),
        "wpm": round(len(words) / max(dsp.get("duration_sec") or est_sec, 1) * 60, 1),
    }
    for n in dsp.get("notes") or []:
        analysis.setdefault("weaknesses", [])
        if n not in analysis["weaknesses"]:
            analysis["weaknesses"].append(n)

    consume_usage(u, int(dsp.get("duration_sec") or est_sec))
    s = Speech(
        user_id=u.id,
        topic=topic,
        text=text,
        score=analysis.get("score", 0),
        analysis=json.dumps(analysis, ensure_ascii=False),
        audio_path=path,
        duration_sec=int(dsp.get("duration_sec") or est_sec),
    )
    db.add(s)
    db.add(AuditLog(user_id=u.id, action="speech_audio", detail=topic))
    db.commit()
    db.refresh(s)
    return {"id": s.id, "plan": effective_plan(u), **analysis}

@router.get("/speech/job/{job_id}")
def speech_job_status(job_id: str, request: Request, db: Session = Depends(get_db)):
    u = current(request, db)
    if not u:
        return JSONResponse({"error": "ابتدا وارد شوید"}, 401)
    job = get_job(job_id)
    if not job:
        return JSONResponse({"error": "job یافت نشد"}, 404)
    return {
        "id": job_id,
        "status": job.get("status"),
        "result": job.get("result"),
        "error": job.get("error"),
    }

@router.get("/speeches")
def speeches(request: Request, db: Session = Depends(get_db)):
    u = current(request, db)
    if not u:
        return JSONResponse({"error": "ابتدا وارد شوید"}, 401)
    rows = db.query(Speech).filter(Speech.user_id == u.id).order_by(Speech.id.desc()).limit(50).all()
    return [
        {
            "id": s.id,
            "topic": s.topic,
            "score": s.score,
            "text": s.text,
            "duration_sec": s.duration_sec,
            "created": s.created_at.isoformat() if s.created_at else None,
            "analysis": json.loads(s.analysis) if s.analysis else {},
        }
        for s in rows
    ]

@router.get("/speech/coach-tip")
async def coach_tip(topic: str = "سخنرانی عمومی"):
    tips = [
        f"برای «{topic}»: با یک جمله جذاب شروع کن.",
        "نفس عمیق، شانه‌ها رها، بعد شروع کن.",
        "بین نکات اصلی یک مکث کوتاه بگذار.",
        "پایان را با جمله به یادماندنی ببند.",
        "انرژی صدا را ثابت و واضح نگه دار.",
    ]
    import random
    return {"tip": random.choice(tips)}
