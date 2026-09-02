# خطیب Production Final v4.1

نسخه Hardened برای Launch تجاری.

## Hardening انجام‌شده

1. **Worker مستقل Redis** — سرویس `worker` در Docker + `python worker.py`
2. **مدت صوت دقیق** — mutagen + ffprobe + تبدیل ffmpeg به WAV برای DSP
3. **DSP بهتر** — انرژی، سکوت، pitch روی سیگنال واقعی
4. **Rate Limit مبتنی بر Redis** (+ fallback حافظه) + محدودیت ورود
5. **Argon2id** برای رمز (با سازگاری PBKDF2 قدیمی)
6. **Monitoring** — `/metrics` + شمارنده + log_error + webhook اختیاری
7. **Backup** — `scripts/backup_pg.sh` و سرویس `backup` در compose
8. **E2E Smoke** — `python scripts/e2e_smoke.py`

## اجرا

```bash
pip install -r requirements.txt
cp .env.example .env
# JWT_SECRET / AI_API_KEY را تنظیم کنید
uvicorn app.main:app --host 0.0.0.0 --port 8000
# در ترمینال جدا (اگر Redis دارید):
REDIS_URL=redis://127.0.0.1:6379/0 python worker.py
```

Docker کامل:
```bash
docker compose up --build
# بکاپ:
docker compose --profile backup run --rm backup
# تست:
python scripts/e2e_smoke.py http://127.0.0.1:8000
```

## Production Checklist

- [ ] JWT_SECRET و PASSWORD_PEPPER تصادفی بلند
- [ ] ENVIRONMENT=production
- [ ] AI_API_KEY واقعی
- [ ] PostgreSQL + Redis
- [ ] COOKIE_SECURE=1 پشت HTTPS
- [ ] ZARINPAL_MERCHANT_ID
- [ ] EITA_BOT_TOKEN در صورت نیاز
- [ ] بکاپ روزانه cron روی backup_pg.sh
