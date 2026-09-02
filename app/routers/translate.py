from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from ..services.ai import translate_text

router = APIRouter()

@router.post("/translate")
async def translate(
    request: Request,
    text: str = Form(""),
    direction: str = Form("auto"),
):
    if not text or not text.strip():
        return JSONResponse({"error": "متن خالی است"}, 400)
    result = await translate_text(text, direction)
    return result