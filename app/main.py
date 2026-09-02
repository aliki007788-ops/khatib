import os
import time
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .core.db import init_db
from .core.security import RateLimitMiddleware
from .core import monitoring
from .routers import auth, speech, chat, billing, topics, admin, translate, eitaa

STARTED_AT = time.time()

app = FastAPI(
    title="خطیب Production Final",
    description="مربی سخنرانی و گویش عراقی — Production Hardened",
    version="4.1.0",
)

origins = os.getenv("CORS_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in origins if o.strip()] or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

@app.middleware("http")
async def count_requests(request: Request, call_next):
    monitoring.inc("requests")
    try:
        return await call_next(request)
    except Exception as e:
        monitoring.log_error("middleware", e, request.url.path)
        raise

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(speech.router, prefix="/api", tags=["speech"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(billing.router, prefix="/api", tags=["billing"])
app.include_router(topics.router, prefix="/api", tags=["topics"])
app.include_router(admin.router, prefix="/api", tags=["admin"])
app.include_router(translate.router, prefix="/api", tags=["translate"])
app.include_router(eitaa.router, prefix="/api", tags=["eitaa"])

static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

_scheduler = None

@app.on_event("startup")
def on_startup():
    global _scheduler
    secret = os.getenv("JWT_SECRET", "")
    bad = {"", "CHANGE_ME", "change_me", "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET",
           "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET_AT_LEAST_32_CHARS", "change_me_please_use_long_secret"}
    if secret in bad:
        print("⚠️  WARNING: JWT_SECRET ناامن است.")
    if os.getenv("ENVIRONMENT", "development") == "production":
        if not (os.getenv("AI_API_KEY") or os.getenv("AI_FALLBACK_KEY")):
            print("❌ PRODUCTION: AI_API_KEY الزامی است.")
    init_db()
    if os.getenv("CRON_ENABLED", "1") == "1":
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from .core.cron_jobs import run_all_maintenance
            _scheduler = BackgroundScheduler(timezone="UTC")
            _scheduler.add_job(run_all_maintenance, "interval", hours=1, id="khatib_maintenance")
            _scheduler.start()
            print("✅ Scheduler فعال")
        except Exception as e:
            monitoring.log_error("scheduler", e)
            print(f"⚠️  Scheduler: {e}")

@app.on_event("shutdown")
def on_shutdown():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)

@app.get("/")
def root():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/health")
def health():
    return {
        "status": "ok",
        "product": "خطیب",
        "version": "4.1.0",
        "uptime_sec": int(time.time() - STARTED_AT),
        "ai_configured": bool(os.getenv("AI_API_KEY") or os.getenv("AI_FALLBACK_KEY")),
        "eitaa_configured": bool(os.getenv("EITA_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")),
        "redis": bool(os.getenv("REDIS_URL")),
        "cron": os.getenv("CRON_ENABLED", "1") == "1",
        "argon2": True,
    }

@app.get("/metrics")
def metrics():
    return monitoring.snapshot() | {"version": "4.1.0"}

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    monitoring.log_error("unhandled", exc, str(request.url.path))
    return JSONResponse({"error": "خطای داخلی سرور"}, status_code=500)
