from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from backend.config import settings

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 20


def create_token(payload: dict) -> str:
    data = payload.copy()
    data["exp"] = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(data, settings.JWT_SECRET, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return {}
