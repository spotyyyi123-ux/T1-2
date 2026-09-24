import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
load_dotenv(PROJECT_ROOT / ".env")


def project_path(value: str | Path) -> Path:
    """Resolve relative storage/legacy file paths against the project, not cwd."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
POLZA_API_KEY = os.getenv("POLZA_API_KEY")
POLZA_API_URL = os.getenv("POLZA_API_URL")
UPLOAD_DIR = project_path(os.getenv("UPLOAD_DIR", "uploads"))
FOLDER_STORAGE_DIR = project_path(os.getenv("FOLDER_STORAGE_DIR", "user_data/folders"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_PROMPT_CHARS = int(os.getenv("MAX_PROMPT_CHARS", "12000"))
# MAX_PROMPT_CHARS now limits each chunk, never truncates the whole document.
CHUNK_OVERLAP_CHARS = int(os.getenv("CHUNK_OVERLAP_CHARS", str(min(800, max(0, MAX_PROMPT_CHARS // 10)))))
MAX_DOCUMENT_CHUNKS = int(os.getenv("MAX_DOCUMENT_CHUNKS", "40"))
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
