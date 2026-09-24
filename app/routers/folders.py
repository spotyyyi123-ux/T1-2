from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database.folder_store import FolderError, FolderStore
from database.models import User
from app.routers.users import get_current_user
from app.core.settings import FOLDER_STORAGE_DIR

router = APIRouter(prefix="/folders", tags=["Folders"])
folder_store = FolderStore(FOLDER_STORAGE_DIR)


class FolderName(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.get("")
def list_folders(current_user: User = Depends(get_current_user)):
    return folder_store.snapshot(current_user.id)["folders"]


@router.post("", status_code=201)
def create_folder(body: FolderName, current_user: User = Depends(get_current_user)):
    try:
        return folder_store.create(current_user.id, body.name)
    except FolderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.patch("/{folder_id}")
def rename_folder(folder_id: str, body: FolderName, current_user: User = Depends(get_current_user)):
    try:
        return folder_store.rename(current_user.id, folder_id, body.name)
    except FolderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.delete("/{folder_id}")
def delete_folder(folder_id: str, current_user: User = Depends(get_current_user)):
    try:
        folder_store.delete(current_user.id, folder_id)
    except FolderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"status": "success", "message": "Папка удалена. Документы перемещены в «Без папки»."}
