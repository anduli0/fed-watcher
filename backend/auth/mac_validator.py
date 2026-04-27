import uuid
import sys
from backend.config import settings


def get_current_mac() -> str:
    raw = uuid.getnode()
    return ":".join(f"{(raw >> (5 - i) * 8) & 0xff:02x}" for i in range(6))


def validate_or_exit():
    if settings.DEV_MODE:
        print("[DEV_MODE] MAC validation skipped.")
        return
    if not settings.OWNER_MAC:
        # MAC not configured yet — block admin routes but allow basic startup
        print("[WARN] OWNER_MAC not set. Run setup.py to lock this server to your hardware.")
        print("[WARN] Admin panel will be inaccessible until OWNER_MAC is configured.")
        return
    current = get_current_mac()
    if current.lower() != settings.OWNER_MAC.lower():
        print(f"[SECURITY] Hardware mismatch. Expected {settings.OWNER_MAC}, got {current}. Access denied.")
        sys.exit(1)
    print(f"[OK] Hardware verified: {current}")
