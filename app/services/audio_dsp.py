"""تحلیل DSP صوت + استخراج دقیق‌تر مدت"""
from __future__ import annotations
import os, struct, math, wave, subprocess, tempfile
from typing import Any

try:
    import numpy as np
    HAS_NP = True
except Exception:
    HAS_NP = False

try:
    from mutagen import File as MutagenFile
    HAS_MUTAGEN = True
except Exception:
    HAS_MUTAGEN = False

def exact_duration_sec(path: str) -> float | None:
    """استخراج مدت واقعی با mutagen یا ffprobe"""
    if not path or not os.path.exists(path):
        return None
    if HAS_MUTAGEN:
        try:
            mf = MutagenFile(path)
            if mf is not None and getattr(mf, "info", None) and getattr(mf.info, "length", None):
                return float(mf.info.length)
        except Exception:
            pass
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            stderr=subprocess.DEVNULL, timeout=15,
        )
        return float(out.decode().strip())
    except Exception:
        return None

def _rms(samples) -> float:
    if not HAS_NP:
        if not samples:
            return 0.0
        return math.sqrt(sum(s * s for s in samples) / len(samples))
    arr = np.asarray(samples, dtype=np.float64)
    return float(np.sqrt(np.mean(arr ** 2))) if arr.size else 0.0

def _estimate_pitch_hz(samples, sr: int) -> float | None:
    if not HAS_NP or sr <= 0 or len(samples) < sr // 10:
        return None
    arr = np.asarray(samples, dtype=np.float64)
    arr = arr - np.mean(arr)
    if np.max(np.abs(arr)) < 1e-9:
        return None
    n = min(len(arr), sr)
    start = max(0, (len(arr) - n) // 2)
    window = arr[start:start + n]
    corr = np.correlate(window, window, mode="full")
    corr = corr[len(corr) // 2:]
    min_lag, max_lag = int(sr / 400), int(sr / 80)
    if max_lag >= len(corr) or min_lag >= max_lag:
        return None
    segment = corr[min_lag:max_lag]
    lag = int(np.argmax(segment)) + min_lag
    return round(sr / lag, 1) if lag > 0 else None

def _read_wav_mono(path: str):
    with wave.open(path, "rb") as w:
        sr, ch, sw, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        data = struct.unpack("<" + ("h" * (len(raw) // 2)), raw)
    elif sw == 1:
        data = [b - 128 for b in raw]
    else:
        return None, None
    mono = list(data[::ch]) if ch > 1 else list(data)
    return mono, sr

def _try_ffmpeg_wav(path: str) -> str | None:
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        subprocess.check_call(
            ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", "16000", tmp.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
        return tmp.name
    except Exception:
        return None

def analyze_audio_file(path: str, fallback_duration_sec: int = 0) -> dict[str, Any]:
    result: dict[str, Any] = {
        "duration_sec": fallback_duration_sec,
        "energy_rms": None,
        "energy_level": "unknown",
        "silence_ratio": None,
        "pitch_hz": None,
        "pitch_note": None,
        "dsp_mode": "estimate",
        "notes": [],
    }
    if not path or not os.path.exists(path):
        result["notes"].append("فایل صوت در دسترس نیست.")
        return result

    dur = exact_duration_sec(path)
    if dur:
        result["duration_sec"] = max(1, int(round(dur)))
        result["notes"].append("مدت از متادیتا/ffprobe استخراج شد.")

    ext = os.path.splitext(path)[1].lower()
    wav_path = path if ext == ".wav" else _try_ffmpeg_wav(path)
    temp_wav = wav_path if wav_path and wav_path != path else None

    samples, sr = None, None
    if wav_path and os.path.exists(wav_path):
        try:
            samples, sr = _read_wav_mono(wav_path)
            result["dsp_mode"] = "wav" if ext == ".wav" else "ffmpeg-wav"
        except Exception as e:
            result["notes"].append(f"WAV decode: {str(e)[:50]}")

    if temp_wav and os.path.exists(temp_wav):
        try:
            os.unlink(temp_wav)
        except Exception:
            pass

    if samples is not None and sr:
        duration = len(samples) / float(sr)
        result["duration_sec"] = max(1, int(round(duration)))
        peak = max(abs(s) for s in samples) or 1
        norm = [s / peak for s in samples]
        rms = _rms(norm)
        result["energy_rms"] = round(rms, 4)
        if rms < 0.05:
            result["energy_level"] = "خیلی ضعیف"
            result["notes"].append("انرژی صدا پایین است.")
        elif rms < 0.15:
            result["energy_level"] = "ضعیف"
            result["notes"].append("صدای شما کمی کم‌جان است.")
        elif rms < 0.45:
            result["energy_level"] = "مناسب"
        else:
            result["energy_level"] = "قوی"

        frame = max(1, int(sr * 0.02))
        silent = total = 0
        for i in range(0, len(norm) - frame, frame):
            total += 1
            if _rms(norm[i:i + frame]) < 0.02:
                silent += 1
        ratio = silent / total if total else 0
        result["silence_ratio"] = round(ratio, 3)
        if ratio > 0.45:
            result["notes"].append("نسبت سکوت بالا است.")
        elif ratio < 0.08 and duration > 20:
            result["notes"].append("مکث بسیار کم است.")

        pitch = _estimate_pitch_hz(norm, sr)
        result["pitch_hz"] = pitch
        if pitch:
            result["pitch_note"] = "بم" if pitch < 110 else ("میانه" if pitch < 180 else "زیر")
        return result

    # fallback بایت
    try:
        size = os.path.getsize(path)
        if not result["duration_sec"]:
            result["duration_sec"] = max(5, min(600, size // 2500))
        if HAS_NP:
            with open(path, "rb") as f:
                chunk = f.read(min(size, 200_000))
            arr = np.frombuffer(chunk, dtype=np.uint8).astype(np.float64) / 255.0
            rms = float(np.sqrt(np.mean((arr - arr.mean()) ** 2)))
            result["energy_rms"] = round(rms, 4)
            result["energy_level"] = "متوسط (تخمینی)"
            result["dsp_mode"] = "container-estimate"
    except Exception as e:
        result["notes"].append(str(e)[:80])
    return result
