import os
import httpx
from datetime import datetime
from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.models import Payment, User, Subscription, AuditLog
from ..core.plans import PLANS, activate_plan, effective_plan, plan_limits, ensure_usage_period
from .auth import current

router = APIRouter()

@router.get("/plans")
def list_plans():
    return [
        {
            "id": k,
            "name": v["name"],
            "price": v["price"],
            "speech_limit": v["speech_limit"],
            "audio_minutes": v["audio_seconds_limit"] // 60,
        }
        for k, v in PLANS.items()
    ]

@router.get("/subscription")
def my_subscription(request: Request, db: Session = Depends(get_db)):
    u = current(request, db)
    if not u:
        return {"error": "ابتدا وارد شوید"}
    ensure_usage_period(u)
    db.commit()
    plan = effective_plan(u)
    limits = plan_limits(plan)
    return {
        "plan": plan,
        "plan_name": limits["name"],
        "expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
        "monthly_speech_count": u.monthly_speech_count or 0,
        "speech_limit": limits["speech_limit"],
        "monthly_audio_seconds": u.monthly_audio_seconds or 0,
        "audio_seconds_limit": limits["audio_seconds_limit"],
    }

@router.post("/subscribe")
async def subscribe(plan: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    u = current(request, db)
    if not u:
        return {"error": "ابتدا وارد شوید"}
    if plan not in PLANS or plan == "free":
        return {"error": "پلن نامعتبر"}
    amount = PLANS[plan]["price"]
    provider = os.getenv("PAYMENT_PROVIDER", "demo").lower()
    p = Payment(user_id=u.id, plan=plan, amount=amount, provider=provider, status="pending")
    db.add(p)
    db.commit()
    db.refresh(p)

    if provider == "demo":
        p.status = "paid"
        activate_plan(u, plan, months=1)
        sub = Subscription(user_id=u.id, plan=plan, active=True, expires_at=u.plan_expires_at)
        db.add(sub)
        db.add(AuditLog(user_id=u.id, action="subscribe_demo", detail=plan))
        db.commit()
        return {"ok": True, "message": f"پلن {PLANS[plan]['name']} فعال شد (آزمایشی)", "payment_id": p.id}

    if provider == "zarinpal":
        merchant = os.getenv("ZARINPAL_MERCHANT_ID", "")
        callback = os.getenv("PAYMENT_CALLBACK_URL", "http://127.0.0.1:8000/api/payment/callback")
        if not merchant:
            return {"ok": False, "message": "ZARINPAL_MERCHANT_ID تنظیم نشده", "payment_id": p.id}
        payload = {
            "merchant_id": merchant,
            "amount": amount,
            "callback_url": callback,
            "description": f"Khatib {plan} #{p.id}",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r = await c.post("https://payment.zarinpal.com/pg/v4/payment/request.json", json=payload)
                data = r.json().get("data", {})
            if data.get("code") == 100:
                p.authority = data.get("authority", "")
                db.commit()
                return {
                    "ok": True,
                    "redirect": f"https://www.zarinpal.com/pg/StartPay/{p.authority}",
                    "message": "به درگاه زرین‌پال منتقل شوید",
                    "payment_id": p.id,
                }
            return {"ok": False, "message": "خطا از درگاه زرین‌پال", "details": data}
        except Exception as e:
            return {"ok": False, "message": f"خطای اتصال به درگاه: {e}"}

    return {"ok": False, "message": "Provider پشتیبانی نشده", "payment_id": p.id}

@router.get("/payment/callback")
async def callback(Authority: str = "", Status: str = "", db: Session = Depends(get_db)):
    p = db.query(Payment).filter_by(authority=Authority).first()
    if not p:
        return {"ok": False, "message": "تراکنش پیدا نشد"}
    if Status != "OK":
        p.status = "cancelled"
        db.commit()
        return {"ok": False, "message": "پرداخت لغو شد"}
    merchant = os.getenv("ZARINPAL_MERCHANT_ID", "")
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://payment.zarinpal.com/pg/v4/payment/verify.json",
                json={"merchant_id": merchant, "amount": p.amount, "authority": Authority},
            )
            data = r.json().get("data", {})
        if data.get("code") in (100, 101):
            p.status = "paid"
            u = db.get(User, p.user_id)
            activate_plan(u, p.plan, months=1)
            sub = Subscription(user_id=u.id, plan=p.plan, active=True, expires_at=u.plan_expires_at)
            db.add(sub)
            db.add(AuditLog(user_id=u.id, action="subscribe_paid", detail=p.plan))
            db.commit()
            return {"ok": True, "message": "پرداخت با موفقیت تأیید شد", "ref_id": data.get("ref_id")}
        p.status = "failed"
        db.commit()
        return {"ok": False, "message": "تأیید پرداخت ناموفق بود"}
    except Exception as e:
        return {"ok": False, "message": f"خطای تأیید: {e}"}
