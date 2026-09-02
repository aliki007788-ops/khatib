"""امنیت Production: Rate Limit مبتنی بر Redis + اعتبارسنجی فایل + Security Headers"""
import time
import os
from collections import defaultdict, deque
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

WINDOW_SEC = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
MAX_REQ = int(os.getenv("RATE_LIMIT_MAX", "90"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
ALLOWED_AUDIO_EXT = {".webm", ".wav", ".mp3", ".ogg", ".m4a", ".mpeg", ".mp4"}
LOGIN_MAX = int(os.getenv("LOGIN_RATE_MAX", "8"))
LOGIN_WINDOW = int(os.getenv("LOGIN_RATE_WINDOW", "300"))

_hits: dict[str, deque] = defaultdict(deque)
_login_hits: dict[str, deque] = defaultdict(deque)

def _redis():
    url = os.getenv("REDIS_URL", "")
    if not url:
        return None
    try:
        import redis
        return redis.from_url(url, decode_responses=True)
    except Exception:
        return None

def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"

def check_rate_limit(request: Request, max_req: int = None, window: int = None, prefix: str = "rl") -> None:
    max_req = max_req or MAX_REQ
    window = window or WINDOW_SEC
    ip = client_ip(request)
    key = f"khatib:{prefix}:{ip}"
    r = _redis()
    now = time.time()
    if r:
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window + 5)
        results = pipe.execute()
        count = results[2]
        if count > max_req:
            raise HTTPException(429, "تعداد درخواست‌ها زیاد است. کمی صبر کنید.")
        return
    # fallback memory
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= max_req:
        raise HTTPException(429, "تعداد درخواست‌ها زیاد است. کمی صبر کنید.")
    q.append(now)

def check_login_rate(request: Request) -> None:
    check_rate_limit(request, max_req=LOGIN_MAX, window=LOGIN_WINDOW, prefix="login")

class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            try:
                if path.rstrip("/").endswith("/login") or path.rstrip("/").endswith("/register"):
                    check_login_rate(request)
                else:
                    check_rate_limit(request)
            except HTTPException as e:
                from fastapi.responses import JSONResponse
                return JSONResponse({"error": e.detail}, status_code=e.status_code)
        response = await call_next(request)
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "microphone=(self), camera=()"
        if os.getenv("COOKIE_SECURE", "0") == "1":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

def validate_audio_upload(filename: str | None, size: int | None) -> None:
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"حجم فایل بیشتر از {MAX_UPLOAD_BYTES // (1024*1024)} مگابایت مجاز نیست.")
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext and ext not in ALLOWED_AUDIO_EXT:
            raise HTTPException(400, f"فرمت صوت مجاز نیست. مجاز: {', '.join(sorted(ALLOWED_AUDIO_EXT))}")
