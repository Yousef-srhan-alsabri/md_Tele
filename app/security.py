from datetime import datetime, timedelta, timezone
from cryptography.fernet import Fernet, InvalidToken
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
cipher = Fernet(settings.session_encryption_key.encode())

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def create_access_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(days=7)}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")

def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None

def encrypt_session(value: str) -> str:
    return cipher.encrypt(value.encode()).decode()

def decrypt_session(value: str) -> str:
    try:
        return cipher.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("تعذر فك تشفير جلسة Telegram") from exc
