import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from database.connection import get_db
from database.models import User
from app.core.settings import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, JWT_SECRET

router = APIRouter(prefix="/users", tags=["Users"])
bearer_scheme = HTTPBearer(auto_error=False)
password_hash = PasswordHash.recommended()


def legacy_hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, stored_hash: str) -> tuple[bool, bool]:
    """Return whether a password is valid and whether its legacy hash needs upgrade."""
    if stored_hash.startswith("$argon2"):
        return password_hash.verify(password, stored_hash), False
    return hmac.compare_digest(legacy_hash_password(password), stored_hash), True


def create_access_token(user_id: int) -> str:
    if not JWT_SECRET:
        raise HTTPException(status_code=503, detail="Не настроен секрет авторизации")
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expires_at}, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not JWT_SECRET or not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется авторизация")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Недействительная сессия")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user

class UserCreate(BaseModel):
    email: EmailStr
    password: str 

class UserResponse(BaseModel):
    id: int
    email: str
    access_token: str
    token_type: str = "bearer"

    class Config:
        from_attributes = True

@router.post("/auth", response_model=UserResponse)
def auth_user(user_data: UserCreate, db: Session = Depends(get_db)):
    if not JWT_SECRET:
        raise HTTPException(status_code=503, detail="Не настроен секрет авторизации")
    user = db.query(User).filter(User.email == user_data.email).first()

    # Вход пользователя: проверяем пароль, если пользователь существует, иначе регистрируем нового пользователя
    if user:
        is_valid, needs_upgrade = verify_password(user_data.password, user.hashed_password)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Неверный пароль"
            )
        if needs_upgrade:
            user.hashed_password = password_hash.hash(user_data.password)
            db.commit()
        return UserResponse(id=user.id, email=user.email, access_token=create_access_token(user.id))
    else:
        # Регистрация нового пользователя, если его нет в базе
        new_user = User(
            email=user_data.email,
            hashed_password=password_hash.hash(user_data.password)
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return UserResponse(id=new_user.id, email=new_user.email, access_token=create_access_token(new_user.id))
