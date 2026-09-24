import asyncio
import logging
import uuid
import zipfile
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import get_db, SessionLocal
from database.models import Document, ExtractedData, Log, User
from app.routers.users import get_current_user
from app.core.settings import MAX_UPLOAD_BYTES, UPLOAD_DIR, project_path
from app.services.extraction_format import AIServiceError, normalize_ai_attributes, display_attributes
from app.core.json_codec import ExactJSONResponse
from app.services.text_extraction import extract_text
from app.services.document_processing import fetch_ai_attributes
from database.folder_store import FolderError
from app.routers.folders import folder_store

# Инициализация роутера (именно эту строчку не мог найти сервер)
router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --- Вспомогательные функции ---

def validate_uploaded_file(file_path: Path, extension: str) -> None:
    """Verify a minimal format signature after writing the upload to disk."""
    with file_path.open("rb") as uploaded:
        header = uploaded.read(8)

    if extension == ".pdf" and not header.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Файл не является корректным PDF")
    if extension == ".docx":
        if not zipfile.is_zipfile(file_path):
            raise HTTPException(status_code=400, detail="Файл не является корректным DOCX")
        with zipfile.ZipFile(file_path) as archive:
            if "word/document.xml" not in archive.namelist():
                raise HTTPException(status_code=400, detail="Файл не является корректным DOCX")


async def save_upload(file: UploadFile, extension: str) -> Path:
    """Stream a file to disk and enforce a server-side size limit."""
    file_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{extension}"
    bytes_written = 0
    try:
        with file_path.open("xb") as destination:
            while chunk := await file.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Файл превышает допустимый размер")
                destination.write(chunk)
        validate_uploaded_file(file_path, extension)
        return file_path
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

# --- Фоновая задача ---

class DocumentProcessingCancelled(Exception):
    """Document was deleted while a provider request was in flight."""

async def process_document_background(document_id: int, file_path: str):
    db = SessionLocal() 
    doc = None
    try:
        doc = db.query(Document).filter(Document.id == document_id).with_for_update().first()
        if not doc:
            return

        doc.status = "processing"
        db.commit()
        raw_text = await asyncio.to_thread(extract_text, file_path)
        
        if not raw_text.strip():
            raise ValueError("Не удалось извлечь текст или файл пуст")

        def report_progress(completed, total):
            current = db.query(Document).filter(Document.id == document_id).populate_existing().with_for_update().first()
            if current is None:
                db.rollback()
                raise DocumentProcessingCancelled()
            message = (f"Документ разбит на {total} частей. Начат полный анализ"
                       if completed == 0 else f"Обработано частей: {completed}/{total}")
            db.add(Log(document_id=document_id, message=message))
            db.commit()

        ai_data = await fetch_ai_attributes(raw_text, on_progress=report_progress)

        # The user may delete this document while extraction/provider work runs.
        doc = db.query(Document).filter(Document.id == document_id).populate_existing().with_for_update().first()
        if not doc:
            return
        
        extracted = ExtractedData(document_id=doc.id, extracted_data=ai_data)
        db.add(extracted)
        
        doc.status = "completed"
        message = ("Анализ всех частей завершён. Есть поля, требующие проверки"
                   if ai_data.get("unparsed_values") else "Анализ всех частей успешно завершён")
        db.add(Log(document_id=doc.id, message=message))
        db.commit()

    except DocumentProcessingCancelled:
        db.rollback()
    except Exception as exc:
        logger.exception("Document processing failed (document_id=%s)", document_id)
        db.rollback()
        doc = db.query(Document).filter(Document.id == document_id).populate_existing().with_for_update().first()
        if doc:
            doc.status = "failed"
            detail = f": {exc}" if isinstance(exc, AIServiceError) else ""
            db.add(Log(document_id=document_id, message=f"Не удалось обработать документ{detail}"))
            db.commit()
    finally:
        db.close()

        
# --- API Эндпоинты ---

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder_id: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    original_name = Path(file.filename or "").name
    extension = Path(original_name).suffix.lower()
    if extension not in {'.pdf', '.docx'}:
        await file.close()
        raise HTTPException(status_code=400, detail="Разрешены только файлы .pdf и .docx")

    file_path = await save_upload(file, extension)

    new_doc = Document(
        user_id=current_user.id,
        filename=original_name,
        file_path=str(file_path),
        status="pending"
    )
    try:
        with folder_store.transaction(current_user.id) as state:
            folder_store.require_folder(state, folder_id)
            db.add(new_doc)
            db.flush()
            folder_store.assign(state, new_doc.id, folder_id)
            db.add(Log(document_id=new_doc.id, message="Файл загружен, ожидает обработки"))
        db.commit()
    except FolderError as exc:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise

    background_tasks.add_task(process_document_background, new_doc.id, str(file_path))

    return {
        "status": "success", 
        "message": "Файл загружен и отправлен в очередь на обработку",
        "document_id": new_doc.id
    }

@router.get("")
def get_user_documents(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    docs = db.query(Document).filter(Document.user_id == current_user.id).order_by(Document.id.desc()).all()
    folder_state = folder_store.snapshot(current_user.id)
    existing_folders = {folder["id"] for folder in folder_state["folders"]}
    
    result = []
    for doc in docs:
        folder_id = folder_state["documents"].get(str(doc.id))
        data = normalize_ai_attributes(doc.extracted_data.extracted_data) if doc.extracted_data else None
        result.append({
            "id": doc.id,
            "filename": doc.filename,
            "status": doc.status,
            "folder_id": folder_id if folder_id in existing_folders else None,
            "uploaded_at": doc.uploaded_at,
            "extracted_data": data,
            "display_data": display_attributes(data) if data is not None else None,
            "logs": [log.message for log in doc.logs]
        })
    # Returning Response directly prevents FastAPI from turning Decimal into float.
    return ExactJSONResponse(result)


class DocumentFolder(BaseModel):
    folder_id: str | None = None


def owned_document(db, user_id, document_id):
    document = db.query(Document).filter(
        Document.id == document_id, Document.user_id == user_id
    ).with_for_update().first()
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    return document


@router.patch("/{document_id}/folder")
def move_document(document_id: int, body: DocumentFolder,
                  db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    owned_document(db, current_user.id, document_id)
    try:
        with folder_store.transaction(current_user.id) as state:
            folder_store.assign(state, document_id, body.folder_id)
        db.commit()  # Release the row lock after the metadata update.
    except FolderError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {"status": "success", "folder_id": body.folder_id}


@router.delete("/{document_id}")
def delete_document(document_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    document = owned_document(db, current_user.id, document_id)
    path = project_path(document.file_path).resolve()
    root = UPLOAD_DIR.resolve()
    if not path.is_relative_to(root) or path == root:
        raise HTTPException(status_code=409, detail="Нельзя удалить файл вне хранилища документов")
    # Old uploads could reuse the same file path. Preserve a shared original.
    shared = db.query(Document).filter(Document.file_path == document.file_path, Document.id != document_id).first()
    staged = None
    try:
        if not shared and path.exists():
            staged = path.with_name(f".deleting-{uuid.uuid4().hex}")
            path.rename(staged)
        db.delete(document)  # Existing ORM cascades delete extraction results and logs.
        db.commit()
    except Exception:
        db.rollback()
        if staged is not None and staged.exists():
            staged.rename(path)
        raise
    cleanup_pending = False
    try:
        if staged is not None:
            staged.unlink(missing_ok=True)
        with folder_store.transaction(current_user.id) as state:
            folder_store.assign(state, document_id, None)
    except OSError:
        cleanup_pending = True
        logger.exception("Deferred file/metadata cleanup for deleted document %s", document_id)
    return {"status": "success", "cleanup_pending": cleanup_pending}
