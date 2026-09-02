"""تعریف پلن‌ها و محدودیت مصرف — قابل ویرایش از یک نقطه"""
from datetime import datetime, timedelta

PLANS = {
    "free": {
        "name": "رایگان",
        "price": 0,
        "speech_limit": 3,          # تعداد تحلیل در ماه
        "audio_seconds_limit": 180, # ۳ دقیقه صوت در ماه
        "days": 0,                  # بدون انقضا (همیشه رایگان با محدودیت)
    },
    "base": {
        "name": "پایه",
        "price": 99000,
        "speech_limit": 30,
        "audio_seconds_limit": 1800,  # ۳۰ دقیقه
        "days": 30,
    },
    "pro": {
        "name": "حرفه‌ای",
        "price": 249000,
        "speech_limit": 9999,
        "audio_seconds_limit": 999999,
        "days": 30,
    },
    "enterprise": {
        "name": "سازمانی",
        "price": 499000,
        "speech_limit": 9999,
        "audio_seconds_limit": 999999,
        "days": 30,
    },
}

def plan_limits(plan: str) -> dict:
    return PLANS.get(plan or "free", PLANS["free"])

def add_months(dt: datetime, months: int = 1) -> datetime:
    try:
        return dt + relativedelta(months=months)
    except Exception:
        return dt + timedelta(days=30 * months)

def ensure_usage_period(user) -> None:
    """اگر ماه عوض شده، شمارنده‌ها را صفر کن"""
    now = datetime.utcnow()
    if not user.usage_reset_at or (now - user.usage_reset_at).days >= 28:
        user.monthly_speech_count = 0
        user.monthly_audio_seconds = 0
        user.usage_reset_at = now

def effective_plan(user) -> str:
    """اگر اشتراک منقضی شده باشد به free برگرد"""
    if user.plan in ("base", "pro", "enterprise"):
        if user.plan_expires_at and user.plan_expires_at < datetime.utcnow():
            return "free"
    return user.plan or "free"

def can_analyze(user, audio_seconds: int = 0) -> tuple[bool, str]:
    ensure_usage_period(user)
    plan = effective_plan(user)
    limits = plan_limits(plan)
    if user.monthly_speech_count >= limits["speech_limit"]:
        return False, f"سقف تعداد تمرین پلن «{limits['name']}» پر شده است. پلن خود را ارتقا دهید."
    if audio_seconds and (user.monthly_audio_seconds + audio_seconds) > limits["audio_seconds_limit"]:
        return False, f"سقف دقیقه صوت پلن «{limits['name']}» پر شده است."
    return True, ""

def consume_usage(user, audio_seconds: int = 0) -> None:
    ensure_usage_period(user)
    user.monthly_speech_count = (user.monthly_speech_count or 0) + 1
    user.monthly_audio_seconds = (user.monthly_audio_seconds or 0) + max(0, audio_seconds)

def activate_plan(user, plan: str, months: int = 1) -> None:
    now = datetime.utcnow()
    user.plan = plan
    if plan == "free":
        user.plan_expires_at = None
    else:
        base = user.plan_expires_at if user.plan_expires_at and user.plan_expires_at > now else now
        user.plan_expires_at = add_months(base, months)
