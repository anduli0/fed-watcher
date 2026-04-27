from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.config import settings
from backend.auth.jwt_handler import verify_token

OPEN_ROUTES = {"/auth/login", "/auth/logout", "/docs", "/openapi.json", "/health"}
OPEN_PREFIXES = ("/api/",)  # 읽기 전용 대시보드 — IP whitelist로 보호됨
PROTECTED_PREFIXES = ("/admin-secure-panel/",)  # 어드민은 항상 인증 필요


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # IP whitelist — skip if ALLOWED_IPS=* (cloud/public deployment)
        if settings.ALLOWED_IPS.strip() != "*":
            # Trust X-Forwarded-For from reverse proxies (Railway, Vercel, Cloudflare)
            forwarded = request.headers.get("x-forwarded-for", "")
            client_ip = forwarded.split(",")[0].strip() if forwarded else (
                request.client.host if request.client else "unknown"
            )
            if client_ip not in settings.allowed_ip_list:
                return JSONResponse({"detail": "Forbidden"}, status_code=403)

        path = request.url.path

        # Skip auth for open routes / public read-only APIs
        if path in OPEN_ROUTES:
            return await call_next(request)
        if any(path.startswith(p) for p in OPEN_PREFIXES) and not any(
            path.startswith(p) for p in PROTECTED_PREFIXES
        ):
            return await call_next(request)

        # JWT validation
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.removeprefix("Bearer ").strip()
        if not token:
            # Try cookie
            token = request.cookies.get("access_token", "")

        payload = verify_token(token)
        if not payload:
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)

        request.state.role = payload.get("role", "deployment")
        request.state.user = payload.get("sub", "owner")
        return await call_next(request)
