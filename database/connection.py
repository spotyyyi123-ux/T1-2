from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.settings import DATABASE_URL
from app.core.json_codec import dumps, loads

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured")

engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                       json_serializer=dumps, json_deserializer=loads)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
