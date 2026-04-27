from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from passlib.context import CryptContext
from backend.auth.jwt_handler import create_token
from backend.config import settings

router = APIRouter(prefix="/auth")
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


class LoginRequest(BaseModel):
    password: str
    role: str = "deployment"  # deployment|admin


@router.post("/login")
async def login(req: LoginRequest, response: Response):
    if not settings.ADMIN_PASSWORD_HASH:
        raise HTTPException(500, "Server not configured. Run setup.py.")
    if not pwd_ctx.verify(req.password, settings.ADMIN_PASSWORD_HASH):
        raise HTTPException(401, "Invalid credentials")

    # Only admin password grants admin role
    granted_role = "admin" if req.role == "admin" else "deployment"
    token = create_token({"sub": "owner", "role": granted_role})

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=72000,  # 20 hours
        samesite="strict",
    )
    return {"access_token": token, "role": granted_role}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"status": "ok"}
