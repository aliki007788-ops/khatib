import os, jwt, datetime, secrets, re
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.models import User, AuditLog
from ..core.plans import effective_plan, plan_limits, ensure_usage_period
from ..core.security import check_login_rate

router = APIRouter()
SECRET = os.getenv("JWT_SECRET", "CHANGE_ME")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

# Argon2id با fallback به PBKDF2
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError
    _ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
    HAS_ARGON = True
except Exception:
    HAS_ARGON = False
    import hashlib, hmac as _hmac
    _ph = None

def hp(password: str) -> str:
    if HAS_ARGON:
        return "argon2:" + _ph.hash(password)
    pepper = os.getenv("PASSWORD_PEPPER", "khatib-default-change-me").encode()
    import hashlib
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), pepper, 260000).hex()
    return "pbkdf2:" + digest

def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("argon2:"):
        if not HAS_ARGON:
            return False
        try:
            return _ph.verify(stored[7:], password)
        except Exception:
            return False
    if stored.startswith("pbkdf2:"):
        import hashlib, hmac
        pepper = os.getenv("PASSWORD_PEPPER", "khatib-default-change-me").encode()
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), pepper, 260000).hex()
        return hmac.compare_digest(stored[7:], digest)
    # legacy plain pbkdf2 hex
    import hashlib, hmac
    pepper = os.getenv("PASSWORD_PEPPER", "khatib-default-change-me").encode()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), pepper, 260000).hex()
    return hmac.compare_digest(stored, digest)

def token(u: User) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {"sub": str(u.id), "iat": int(now.timestamp()), "exp": now + datetime.timedelta(days=7)},
        SECRET,
        algorithm="HS256",
    )

def current(request: Request, db: Session = Depends(get_db)):
    t = request.cookies.get("access_token")
    if not t:
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            t = auth[7:].strip()
    if not t:
        return None
    try:
        uid = int(jwt.decode(t, SECRET, algorithms=["HS256"])["sub"])
    except Exception:
        return None
    u = db.get(User, uid)
    return u if u and u.active else None

def public(u: User) -> dict:
    ensure_usage_period(u)
    plan = effective_plan(u)
    limits = plan_limits(plan)
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "plan": plan,
        "plan_name": limits["name"],
        "plan_expires_at": u.plan_expires_at.isoformat() if u.plan_expires_at else None,
        "monthly_speech_count": u.monthly_speech_count or 0,
        "speech_limit": limits["speech_limit"],
        "role": u.role,
    }

@router.post("/register")
def register(email: str = Form(...), password: str = Form(...), name: str = Form("کاربر"), request: Request = None, db: Session = Depends(get_db)):
    if request is not None:
        try:
            check_login_rate(request)
        except Exception as e:
            from fastapi import HTTPException
            if isinstance(e, HTTPException):
                return JSONResponse({"error": e.detail}, e.status_code)
    email = email.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return JSONResponse({"error": "ایمیل نامعتبر است"}, 400)
    if len(password) < 8:
        return JSONResponse({"error": "رمز عبور باید حداقل ۸ کاراکتر باشد"}, 400)
    if db.query(User).filter_by(email=email).first():
        return JSONResponse({"error": "این ایمیل قبلاً ثبت شده است"}, 400)
    u = User(email=email, password_hash=hp(password), name=(name.strip() or "کاربر")[:120])
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(AuditLog(user_id=u.id, action="register", detail=email))
    db.commit()
    r = JSONResponse({"ok": True, "user": public(u)})
    r.set_cookie("access_token", token(u), httponly=True, samesite="lax", secure=COOKIE_SECURE, max_age=604800, path="/")
    return r

@router.post("/login")
def login(email: str = Form(...), password: str = Form(...), request: Request = None, db: Session = Depends(get_db)):
    if request is not None:
        try:
            check_login_rate(request)
        except Exception as e:
            from fastapi import HTTPException
            if isinstance(e, HTTPException):
                return JSONResponse({"error": e.detail}, e.status_code)
    u = db.query(User).filter_by(email=email.strip().lower(), active=True).first()
    if not u or not verify_password(password, u.password_hash):
        return JSONResponse({"error": "اطلاعات ورود نادرست است"}, 401)
    # rehash to argon2 if legacy
    if HAS_ARGON and not u.password_hash.startswith("argon2:"):
        u.password_hash = hp(password)
        db.commit()
    r = JSONResponse({"ok": True, "user": public(u)})
    r.set_cookie("access_token", token(u), httponly=True, samesite="lax", secure=COOKIE_SECURE, max_age=604800, path="/")
    return r

@router.post("/logout")
def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie("access_token", path="/")
    return r

@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    u = current(request, db)
    if u:
        db.commit()
    return {"logged": bool(u), "user": public(u) if u else None}
