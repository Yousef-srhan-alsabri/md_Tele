from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.security import decode_access_token

COOKIE_NAME = "access_token"

def get_current_user(access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    user_id = decode_access_token(access_token or "")
    user = db.get(User, user_id) if user_id else None
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="يجب تسجيل الدخول")
    return user

def get_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="صلاحية المشرف مطلوبة")
    return user
