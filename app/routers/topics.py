from fastapi import APIRouter,Depends,Request,Form
from sqlalchemy.orm import Session
from ..core.db import get_db
from ..core.models import Topic
from .auth import current
router=APIRouter()
@router.get("/topics")
def list_topics(db:Session=Depends(get_db)):
 return [{"id":t.id,"name":t.name,"category":t.category} for t in db.query(Topic).filter_by(active=True).all()]
@router.post("/topics")
def add_topic(name:str=Form(...),category:str=Form("عمومی"),prompt:str=Form(""),request:Request=None,db:Session=Depends(get_db)):
 u=current(request,db)
 if not u or u.role!="admin":return {"error":"دسترسی مدیر لازم است"}
 t=Topic(name=name,category=category,prompt=prompt);db.add(t);db.commit();return {"ok":True,"id":t.id}
