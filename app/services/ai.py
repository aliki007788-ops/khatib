import os
import httpx
import json
import re

AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini")
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")
# Provider دوم اختیاری (مثلاً Groq)
AI_FALLBACK_KEY = os.getenv("AI_FALLBACK_KEY", "")
AI_FALLBACK_BASE = os.getenv("AI_FALLBACK_BASE", "https://api.groq.com/openai/v1")
AI_FALLBACK_MODEL = os.getenv("AI_FALLBACK_MODEL", "llama-3.3-70b-versatile")

async def _chat(messages: list, temperature: float = 0.4, json_mode: bool = False) -> str | None:
    providers = []
    if AI_API_KEY:
        providers.append((AI_BASE_URL, AI_API_KEY, AI_MODEL))
    if AI_FALLBACK_KEY:
        providers.append((AI_FALLBACK_BASE, AI_FALLBACK_KEY, AI_FALLBACK_MODEL))
    if not providers:
        return None

    for base, key, model in providers:
        try:
            payload = {"model": model, "messages": messages, "temperature": temperature}
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{base.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except Exception:
            continue
    return None

async def transcribe(path: str) -> str:
    if not AI_API_KEY and not AI_FALLBACK_KEY:
        if os.getenv("ENVIRONMENT", "development") == "production":
            return "خطا: سرویس تشخیص گفتار در Production بدون AI_API_KEY در دسترس نیست."
        return "متن نمونه: سلام، امروز می‌خواهم درباره اعتماد به نفس در سخنرانی صحبت کنم. سه نکته مهم دارم و در پایان جمع‌بندی می‌کنم."
    providers = []
    if AI_API_KEY:
        providers.append((AI_BASE_URL, AI_API_KEY, STT_MODEL))
    if AI_FALLBACK_KEY:
        providers.append((AI_FALLBACK_BASE, AI_FALLBACK_KEY, "whisper-large-v3"))

    for base, key, model in providers:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                with open(path, "rb") as f:
                    files = {"file": (os.path.basename(path), f, "audio/webm")}
                    data = {"model": model, "language": "fa"}
                    r = await client.post(
                        f"{base.rstrip('/')}/audio/transcriptions",
                        headers={"Authorization": f"Bearer {key}"},
                        files=files,
                        data=data,
                    )
                    if r.status_code == 200:
                        return r.json().get("text", "") or ""
        except Exception:
            continue
    return "نتوانستم صدا را تشخیص دهم. لطفاً دوباره و واضح‌تر ضبط کنید."

def _local_coaching(text: str, topic: str) -> dict:
    words = re.findall(r"[\wآ-ی]+", text or "")
    n = len(words)
    sentences = max(1, len(re.findall(r"[.!؟?؛\n]", text or "")))
    avg = round(n / sentences, 1)
    fillers = ["یعنی", "مثلاً", "مثلا", "در واقع", "حالا", "خب"]
    filler_n = sum(1 for w in words if w in fillers)
    score = 40
    if n >= 40: score += 15
    if n >= 90: score += 15
    if sentences >= 4: score += 10
    if avg <= 25: score += 10
    if filler_n <= 2: score += 5
    if n < 25: score = min(score, 35)
    score = max(15, min(95, score))

    strengths, weaknesses, improvements = [], [], []
    if n >= 60: strengths.append("حجم محتوای قابل قبول")
    if sentences >= 4: strengths.append("تقسیم به چند جمله")
    if filler_n <= 1: strengths.append("کلمات پرکننده کم")
    if not strengths: strengths.append("تلاش برای شروع تمرین")

    if n < 50: weaknesses.append("متن کوتاه است؛ مقدمه و جمع‌بندی اضافه کنید")
    if avg > 30: weaknesses.append("جملات طولانی؛ کوتاه‌تر صحبت کنید")
    if filler_n >= 3: weaknesses.append(f"تکرار کلمات پرکننده ({filler_n} بار)")
    if not weaknesses: weaknesses.append("می‌توانید انرژی پایان را قوی‌تر کنید")

    improvements = [
        "با یک سؤال یا جمله جذاب شروع کنید",
        "۲ یا ۳ نکته اصلی را شماره‌گذاری کنید",
        "پایان را با یک جمله به یادماندنی ببندید",
    ]
    return {
        "score": score,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "improvements": improvements,
        "structure_notes": "ساختار پیشنهادی: مقدمه ۲۰٪ | بدنه ۶۰٪ | جمع‌بندی ۲۰٪",
        "next_practice": f"موضوع «{topic or 'همین موضوع'}» را ۶۰ ثانیه با مکث‌های آگاهانه دوباره اجرا کنید.",
        "transcript": text,
        "ai_mode": "local",
    }

async def generate_coaching_feedback(text: str, topic: str = "") -> dict:
    if not text or len(text.strip()) < 8:
        return {
            "score": 20,
            "strengths": [],
            "weaknesses": ["متن خیلی کوتاه است."],
            "improvements": ["حداقل ۴۵ تا ۶۰ ثانیه صحبت کنید."],
            "structure_notes": "مقدمه، بدنه و جمع‌بندی مشخص نیست.",
            "next_practice": "با یک مقدمه ۲۰ ثانیه‌ای دوباره شروع کنید.",
            "transcript": text or "",
            "ai_mode": "local",
        }

    prompt = f"""تو مربی حرفه‌ای سخنرانی برای فارسی‌زبانان هستی (اپ خطیب).
موضوع: {topic or 'آزاد'}
متن سخنرانی:
\"\"\"{text}\"\"\"

فقط JSON خالص با کلیدهای:
score (0-100), strengths (list), weaknesses (list), improvements (list),
structure_notes (string), next_practice (string)
لحن گرم و مربی‌گونه، فارسی روان."""

    content = await _chat(
        [
            {"role": "system", "content": "فقط JSON معتبر برگردان بدون markdown."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
    )
    if content:
        try:
            content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(content)
            data["transcript"] = text
            data["ai_mode"] = "remote"
            return data
        except Exception:
            pass
    return _local_coaching(text, topic)

async def chat_iraqi_coach(message: str, history: list | None = None) -> str:
    system = """تو مربی اپ «خطیب» هستی.
کمک به فارسی‌زبانان برای سخنرانی و مکالمه گویش عراقی عامیانه.
گاهی عراقی بگو و بلافاصله ترجمه فارسی کوتاه بگذار.
لحن گرم و اصلاح مودبانه."""
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history[-8:])
    messages.append({"role": "user", "content": message})
    ans = await _chat(messages, temperature=0.7)
    if ans:
        return ans
    return "أهلاً! شلونک؟ من مربی خطیب هستم. برای تمرین سخنرانی موضوع بگو یا از بخش سخنرانی اپ استفاده کن."

async def translate_text(text: str, direction: str = "auto") -> dict:
    if not text.strip():
        return {"translated": "", "detected": "unknown", "sub": ""}
    prompt = f"""اگر متن فارسی است به گویش عراقی بغدادی ترجمه کن.
اگر عراقی/عربی است به فارسی روان ترجمه کن.
فقط JSON: {{"translated":"...","detected":"fa یا ar-iq","sub":"توضیح کوتاه"}}
متن: {text}"""
    content = await _chat(
        [{"role": "system", "content": "فقط JSON."}, {"role": "user", "content": prompt}],
        temperature=0.25,
    )
    if content:
        try:
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content)
        except Exception:
            pass
    has_fa = any("\u0600" <= c <= "\u06FF" for c in text)
    if has_fa:
        return {"translated": "أهلاً! شلونك؟ شكو ماكو؟", "detected": "fa", "sub": "نمونه عراقی (حالت بدون AI)"}
    return {"translated": "سلام! چطوری؟ چه خبر؟", "detected": "ar-iq", "sub": "نمونه فارسی (حالت بدون AI)"}
