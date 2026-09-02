"""کرون داخلی: انقضای اشتراک، ریست ماهانه مصرف، تمدید یادآوری"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import User, Subscription, AuditLog
from .plans import ensure_usage_period, activate_plan

def expire_subscriptions(db: Session | None = None) -> dict:
    own = False
    if db is None:
        db = SessionLocal()
        own = True
    try:
        now = datetime.utcnow()
        users = db.query(User).filter(
            User.plan.in_(["base", "pro", "enterprise"]),
            User.plan_expires_at != None,
            User.plan_expires_at < now,
        ).all()
        count = 0
        for u in users:
            u.plan = "free"
            u.plan_expires_at = None
            db.query(Subscription).filter_by(user_id=u.id, active=True).update({"active": False})
            db.add(AuditLog(user_id=u.id, action="subscription_expired", detail="auto"))
            count += 1
        db.commit()
        return {"expired": count}
    finally:
        if own:
            db.close()

def reset_monthly_usage(db: Session | None = None) -> dict:
    own = False
    if db is None:
        db = SessionLocal()
        own = True
    try:
        now = datetime.utcnow()
        users = db.query(User).all()
        n = 0
        for u in users:
            if not u.usage_reset_at or (now - u.usage_reset_at).days >= 28:
                u.monthly_speech_count = 0
                u.monthly_audio_seconds = 0
                u.usage_reset_at = now
                n += 1
        db.commit()
        return {"reset_users": n}
    finally:
        if own:
            db.close()

def auto_renew_demo_subscriptions(db: Session | None = None) -> dict:
    """
    تمدید خودکار برای کاربرانی که flag تمدید دارند.
    در مدل فعلی از Subscription.active + plan استفاده می‌کنیم.
    اگر PAYMENT_PROVIDER=demo باشد می‌تواند یک ماه دیگر فعال کند.
    در Production واقعی باید به درگاه وصل شود؛ اینجا ساختار آماده است.
    """
    import os
    own = False
    if db is None:
        db = SessionLocal()
        own = True
    try:
        if os.getenv("AUTO_RENEW_ENABLED", "0") != "1":
            return {"renewed": 0, "note": "AUTO_RENEW_ENABLED=0"}
        now = datetime.utcnow()
        soon = now + timedelta(days=1)
        # اشتراک‌هایی که فردا منقضی می‌شوند و هنوز active هستند
        subs = db.query(Subscription).filter(
            Subscription.active == True,
            Subscription.expires_at != None,
            Subscription.expires_at <= soon,
            Subscription.expires_at > now - timedelta(days=1),
        ).all()
        renewed = 0
        provider = os.getenv("PAYMENT_PROVIDER", "demo").lower()
        for sub in subs:
            u = db.get(User, sub.user_id)
            if not u or not u.active:
                continue
            if provider == "demo":
                activate_plan(u, sub.plan, months=1)
                sub.expires_at = u.plan_expires_at
                db.add(AuditLog(user_id=u.id, action="auto_renew_demo", detail=sub.plan))
                renewed += 1
            else:
                # در حالت زرین‌پال: فقط لاگ یادآوری — شارژ واقعی نیاز به توکن ذخیره کارت دارد
                db.add(AuditLog(user_id=u.id, action="renew_reminder", detail=sub.plan))
        db.commit()
        return {"renewed": renewed, "provider": provider}
    finally:
        if own:
            db.close()

def run_all_maintenance() -> dict:
    return {
        "expire": expire_subscriptions(),
        "usage_reset": reset_monthly_usage(),
        "renew": auto_renew_demo_subscriptions(),
        "at": datetime.utcnow().isoformat(),
    }
