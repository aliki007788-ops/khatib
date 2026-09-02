from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.models import User, Payment, Speech, AuditLog
from ..core.plans import effective_plan, plan_limits, activate_plan
from ..routers.auth import current

router = APIRouter()

def adm(request, db):
    u = current(request, db)
    if not u or u.role != "admin":
        raise HTTPException(403, "دسترسی مدیر لازم است")
    return u

@router.get("/stats")
def stats(request: Request, db: Session = Depends(get_db)):
    adm(request, db)
    paid = db.query(Payment).filter_by(status="paid").all()
    return {
        "users": db.query(User).count(),
        "speeches": db.query(Speech).count(),
        "payments": db.query(Payment).count(),
        "revenue": sum((p.amount for p in paid), 0),
        "active_paid_users": db.query(User).filter(User.plan.in_(["base", "pro", "enterprise"])).count(),
        "speeches_today": db.query(Speech).filter(Speech.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)).count(),
    }

@router.get("/users")
def users(request: Request, db: Session = Depends(get_db)):
    adm(request, db)
    out = []
    for u in db.query(User).order_by(User.id.desc()).all():
        plan = effective_plan(u)
        limits = plan_limits(plan)
        out.append({
            "id": u.id,
            "email": u.email,
            "name": u.name,
            "plan": plan,
            "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
            "monthly_speech_count": u.monthly_speech_count or 0,
            "speech_limit": limits["speech_limit"],
            "monthly_audio_seconds": u.monthly_audio_seconds or 0,
            "role": u.role,
            "active": u.active,
        })
    return out

@router.get("/audit")
def audit(request: Request, db: Session = Depends(get_db), limit: int = 80):
    adm(request, db)
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "action": a.action,
            "detail": a.detail,
            "created": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]

@router.post("/make-admin/{uid}")
def make_admin(uid: int, request: Request, db: Session = Depends(get_db)):
    adm(request, db)
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "کاربر یافت نشد")
    u.role = "admin"
    db.commit()
    return {"ok": True}

@router.post("/users/{uid}/reset-usage")
def reset_usage(uid: int, request: Request, db: Session = Depends(get_db)):
    adm(request, db)
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "کاربر یافت نشد")
    u.monthly_speech_count = 0
    u.monthly_audio_seconds = 0
    u.usage_reset_at = datetime.utcnow()
    db.add(AuditLog(user_id=uid, action="admin_reset_usage", detail=str(uid)))
    db.commit()
    return {"ok": True}

@router.post("/users/{uid}/set-plan")
def set_plan(uid: int, plan: str, request: Request, db: Session = Depends(get_db)):
    adm(request, db)
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "کاربر یافت نشد")
    if plan not in ("free", "base", "pro", "enterprise"):
        raise HTTPException(400, "پلن نامعتبر")
    activate_plan(u, plan, months=1 if plan != "free" else 0)
    db.add(AuditLog(user_id=uid, action="admin_set_plan", detail=plan))
    db.commit()
    return {"ok": True, "plan": plan, "expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None}

@router.post("/users/{uid}/deactivate")
def deactivate(uid: int, request: Request, db: Session = Depends(get_db)):
    adm(request, db)
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "کاربر یافت نشد")
    u.active = False
    db.add(AuditLog(user_id=uid, action="admin_deactivate", detail=""))
    db.commit()
    return {"ok": True}


@router.post("/run-maintenance")
def run_maintenance(request: Request, db: Session = Depends(get_db)):
    adm(request, db)
    from ..core.cron_jobs import run_all_maintenance
    return run_all_maintenance()
