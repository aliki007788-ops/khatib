from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.models import Conversation, Message
from .auth import current
from ..services.ai import chat_iraqi_coach

router = APIRouter()

@router.get("/conversations")
def convs(request: Request, db: Session = Depends(get_db)):
    u = current(request, db)
    if not u:
        return JSONResponse({"error": "ابتدا وارد شوید"}, 401)
    return [{"id": c.id, "title": c.title} for c in db.query(Conversation).filter_by(user_id=u.id).order_by(Conversation.id.desc()).all()]

@router.get("/conversations/{cid}")
def convo(cid: int, request: Request, db: Session = Depends(get_db)):
    u = current(request, db)
    c = db.get(Conversation, cid)
    if not u or not c or c.user_id != u.id:
        return JSONResponse({"error": "دسترسی ندارید"}, 403)
    return [{"role": m.role, "content": m.content} for m in db.query(Message).filter_by(conversation_id=cid).order_by(Message.id).all()]

@router.post("/conversations")
def new_conversation(request: Request, title: str = Form("گفتگوی جدید"), db: Session = Depends(get_db)):
    u = current(request, db)
    if not u:
        return JSONResponse({"error": "ابتدا وارد شوید"}, 401)
    c = Conversation(user_id=u.id, title=title[:200])
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "title": c.title}

@router.post("/chat")
async def chat(
    message: str = Form(...),
    conversation_id: int | None = Form(None),
    request: Request = None,
    db: Session = Depends(get_db)
):
    u = current(request, db)
    if not u:
        return JSONResponse({"error": "ابتدا وارد شوید"}, 401)
    c = db.get(Conversation, conversation_id) if conversation_id else None
    if not c or c.user_id != u.id:
        c = Conversation(user_id=u.id, title=message.strip()[:60] or "گفتگوی جدید")
        db.add(c)
        db.commit()
        db.refresh(c)
    db.add(Message(conversation_id=c.id, role="user", content=message.strip()))
    db.commit()
    history = [
        {"role": m.role, "content": m.content}
        for m in db.query(Message).filter_by(conversation_id=c.id).order_by(Message.id.desc()).limit(16).all()
    ][::-1]
    # remove system if any, chat_iraqi_coach handles system
    history = [h for h in history if h["role"] in ("user", "assistant")]
    answer = await chat_iraqi_coach(message.strip(), history[:-1] if history else None)
    db.add(Message(conversation_id=c.id, role="assistant", content=answer))
    db.commit()
    return {"answer": answer, "conversation_id": c.id}
