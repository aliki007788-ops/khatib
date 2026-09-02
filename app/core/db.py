import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
os.makedirs(os.path.join(BASE,"data"),exist_ok=True)
url=os.getenv("DATABASE_URL","sqlite:///"+os.path.join(BASE,"data","khatib.db"))
if url.startswith("postgres://"): url=url.replace("postgres://","postgresql+psycopg://",1)
elif url.startswith("postgresql://"): url=url.replace("postgresql://","postgresql+psycopg://",1)
engine=create_engine(url,connect_args={"check_same_thread":False} if url.startswith("sqlite") else {},pool_pre_ping=True)
SessionLocal=sessionmaker(bind=engine,autocommit=False,autoflush=False)
class Base(DeclarativeBase): pass
def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()
def init_db():
    from .models import User,Speech,Conversation,Message,Payment,Topic,AuditLog,Subscription
    Base.metadata.create_all(engine)
