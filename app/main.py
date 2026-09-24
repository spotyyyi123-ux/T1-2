import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from database.connection import engine
from database.base import Base
from database import models  # Register the unchanged SQLAlchemy tables.
from app.routers import users, documents, folders
from app.core.settings import FRONTEND_DIR

@asynccontextmanager
async def lifespan(application: FastAPI):
    # Same initialization as before, but only at server startup, not on import.
    Base.metadata.create_all(bind=engine)
    yield

# Инициализируем приложение FastAPI
app = FastAPI(
    title="Smart Contract Parser API",
    description="Модульный MVP парсера договоров на базе NLP/LLM и фоновых задач",
    version="3.0",
    lifespan=lifespan,
)

# Подключаем HTTP-роутеры приложения.
app.include_router(users.router, prefix="/api")
app.include_router(documents.router, prefix="/api")
app.include_router(folders.router, prefix="/api")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

# Отдаем фронтенд
@app.get("/", response_class=HTMLResponse, tags=["Frontend"])
def read_index():
    try:
        with (FRONTEND_DIR / "index.html").open("r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse("<h1>Файл frontend/index.html не найден</h1>", status_code=500)

if __name__ == "__main__":
    # Запуск из корня проекта: python -m app.main
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
