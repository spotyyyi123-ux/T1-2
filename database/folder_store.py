"""File-backed per-user folder metadata; no changes to the approved DB schema.

The data directory must be persistent and backed up together with uploads and
PostgreSQL. flock + atomic replacement protect concurrent local server workers.
All server instances must share this directory (not separate ephemeral disks).
"""

import copy
import fcntl
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class FolderError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


class FolderStore:
    def __init__(self, root):
        self.root = Path(root)

    @contextmanager
    def transaction(self, user_id):
        if not isinstance(user_id, int) or user_id <= 0:
            raise ValueError("Invalid user ID")
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{user_id}.json"
        with (self.root / f"{user_id}.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if target.exists():
                    with target.open(encoding="utf-8") as stream:
                        state = json.load(stream)
                else:
                    state = {"version": 1, "folders": [], "documents": {}}
                previous = copy.deepcopy(state)
                yield state
                if state != previous:
                    temporary = None
                    try:
                        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, delete=False) as stream:
                            temporary = Path(stream.name)
                            json.dump(state, stream, ensure_ascii=False)
                            stream.flush()
                            os.fsync(stream.fileno())
                        os.replace(temporary, target)
                    finally:
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def snapshot(self, user_id):
        with self.transaction(user_id) as state:
            return copy.deepcopy(state)

    @staticmethod
    def require_folder(state, folder_id):
        if folder_id is None:
            return
        if not any(folder["id"] == folder_id for folder in state["folders"]):
            raise FolderError("Папка не найдена", 404)

    @staticmethod
    def validate_name(state, name, excluding=None):
        name = " ".join(name.split())
        if not name or len(name) > 80:
            raise FolderError("Название папки должно содержать от 1 до 80 символов")
        if any(ord(char) < 32 or char in '/\\' for char in name):
            raise FolderError("Название папки не должно содержать слеши или управляющие символы")
        if any(folder["id"] != excluding and folder["name"].casefold() == name.casefold() for folder in state["folders"]):
            raise FolderError("Папка с таким названием уже существует", 409)
        return name

    def create(self, user_id, name):
        with self.transaction(user_id) as state:
            name = self.validate_name(state, name)
            folder = {"id": uuid.uuid4().hex, "name": name, "created_at": datetime.now(timezone.utc).isoformat()}
            state["folders"].append(folder)
        return folder

    def rename(self, user_id, folder_id, name):
        with self.transaction(user_id) as state:
            self.require_folder(state, folder_id)
            name = self.validate_name(state, name, excluding=folder_id)
            folder = next(folder for folder in state["folders"] if folder["id"] == folder_id)
            folder["name"] = name
        return folder

    def delete(self, user_id, folder_id):
        with self.transaction(user_id) as state:
            self.require_folder(state, folder_id)
            state["folders"] = [folder for folder in state["folders"] if folder["id"] != folder_id]
            state["documents"] = {doc: parent for doc, parent in state["documents"].items() if parent != folder_id}

    @staticmethod
    def assign(state, document_id, folder_id):
        FolderStore.require_folder(state, folder_id)
        if folder_id is None:
            state["documents"].pop(str(document_id), None)
        else:
            state["documents"][str(document_id)] = folder_id
