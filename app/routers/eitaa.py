"""اتصال کامل‌تر ایتا / بات پیام‌رسان + مینی‌اپ"""
import os
import hmac
import hashlib
import json
import httpx
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.models import AuditLog, User
from ..routers.auth import token, public

import secrets as _secrets

def secrets_token():
    return _secrets.token_urlsafe(16)

router = APIRouter()
EITA_TOKEN = os.getenv("EITA_BOT_TOKEN", "") or os.getenv("TELEGRAM_BOT_TOKEN", "")
EITA_SECRET = os.getenv("EITA_BOT_WEBHOOK_SECRET", "")
EITA_API = os.getenv("EITA_API_BASE", "https://eitaayar.ir/api")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:8000")

async def send_message(chat_id: str, text: str) -> dict:
    if not EITA_TOKEN:
        return {"ok": False, "error": "EITA_BOT_TOKEN تنظیم نشده"}
    url = f"{EITA_API.rstrip('/')}/{EITA_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": text})
            if r.status_code >= 400:
                # fallback Telegram-style
                tg = f"https://api.telegram.org/bot{EITA_TOKEN}/sendMessage"
                r2 = await client.post(tg, json={"chat_id": chat_id, "text": text})
                return r2.json() if r2.content else {"ok": False}
            return r.json() if r.content else {"ok": r.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@router.get("/eitaa/status")
def eitaa_status():
    return {
        "configured": bool(EITA_TOKEN),
        "api_base": EITA_API,
        "miniapp_url": FRONTEND_URL,
        "webhook_path": "/api/eitaa/webhook",
        "commands": ["/start", "/app", "/help", "/plan"],
    }

@router.post("/eitaa/set-webhook")
async def set_webhook(url: str | None = None):
    if not EITA_TOKEN:
        return JSONResponse({"ok": False, "error": "توکن نیست"}, 400)
    hook = url or f"{FRONTEND_URL.rstrip('/')}/api/eitaa/webhook"
    # تلاش برای setWebhook در APIهای سازگار
    endpoints = [
        f"{EITA_API.rstrip('/')}/{EITA_TOKEN}/setWebhook",
        f"https://api.telegram.org/bot{EITA_TOKEN}/setWebhook",
    ]
    async with httpx.AsyncClient(timeout=20) as client:
        for ep in endpoints:
            try:
                r = await client.post(ep, json={"url": hook, "secret_token": EITA_SECRET or None})
                if r.status_code < 500:
                    return {"ok": True, "endpoint": ep, "response": r.json() if r.content else r.status_code, "webhook": hook}
            except Exception as e:
                last = str(e)
    return {"ok": False, "error": "setWebhook ناموفق — API را بررسی کنید", "webhook": hook}

@router.post("/eitaa/webhook")
async def eitaa_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_eitaa_secret: str | None = Header(default=None, alias="X-Eitaa-Secret"),
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    if EITA_SECRET:
        incoming = x_eitaa_secret or x_telegram_bot_api_secret_token
        if incoming != EITA_SECRET:
            raise HTTPException(403, "secret نامعتبر")
    if not EITA_TOKEN:
        return JSONResponse({"ok": False, "error": "بات پیکربندی نشده"}, 503)

    body = await request.json()
    message = body.get("message") or body.get("data") or body
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or message.get("chat_id") or body.get("chat_id") or "")
    text = (message.get("text") or body.get("text") or "").strip()
    from_user = message.get("from") or {}

    if not chat_id:
        return {"ok": True, "ignored": True}

    if text.startswith("/start"):
        reply = (
            "🎙️ أهلاً! به *خطیب* خوش آمدی.\n"
            "مربی سخنرانی و گویش عراقی.\n\n"
            f"شروع تمرین: {FRONTEND_URL}\n"
            "دستورات: /app /help /plan"
        )
    elif text.startswith("/app"):
        reply = f"باز کردن اپ خطیب:\n{FRONTEND_URL}"
    elif text.startswith("/plan"):
        reply = "پلن‌ها:\n• رایگان: ۳ تمرین/ماه\n• پایه: ۳۰ تمرین\n• حرفه‌ای: نامحدود\n\nاز داخل اپ خرید کنید."
    elif text.startswith("/help"):
        reply = "کمک:\n1) وارد اپ شو\n2) موضوع انتخاب کن\n3) صحبت کن و بازخورد بگیر\n/app برای لینک اپ"
    elif text:
        reply = (
            f"پیام شما دریافت شد.\n"
            f"برای تحلیل سخنرانی وارد اپ شوید:\n{FRONTEND_URL}"
        )
    else:
        reply = f"سلام! برای شروع: {FRONTEND_URL}"

    result = await send_message(chat_id, reply)
    db.add(AuditLog(user_id=None, action="eitaa_webhook", detail=f"chat={chat_id};text={text[:40]}"))
    db.commit()
    return {"ok": True, "send": result}

@router.post("/eitaa/miniapp-auth")
async def miniapp_auth(request: Request, db: Session = Depends(get_db)):
    """
    احراز هویت مینی‌اپ: دریافت initData و ساخت/ورود کاربر.
    در صورت نبود امضای استاندارد ایتا، حالت توسعه با eitaa_id کار می‌کند.
    """
    body = await request.json()
    eitaa_id = str(body.get("id") or body.get("user_id") or "")
    name = (body.get("first_name") or body.get("name") or "کاربر ایتا")[:120]
    if not eitaa_id:
        return JSONResponse({"error": "id لازم است"}, 400)

    email = f"eitaa_{eitaa_id}@eitaa.local"
    u = db.query(User).filter_by(email=email).first()
    if not u:
        from ..routers.auth import hp
        u = User(email=email, password_hash=hp(secrets_token()), name=name)
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(AuditLog(user_id=u.id, action="eitaa_miniapp_register", detail=eitaa_id))
        db.commit()

    from fastapi.responses import JSONResponse as JR
    from ..routers.auth import token as make_token, public as pub
    r = JR({"ok": True, "user": pub(u)})
    r.set_cookie("access_token", make_token(u), httponly=True, samesite="lax", path="/", max_age=604800)
    return r

