"""
First-time setup: register this machine's MAC, generate JWT secret, hash admin password.
Run once: python setup.py
"""
import uuid
import secrets
import getpass
from pathlib import Path
from passlib.context import CryptContext

ENV_FILE = Path("C:/Users/andul/fed-watcher/.env")
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_mac() -> str:
    raw = uuid.getnode()
    return ":".join(f"{(raw >> (5 - i) * 8) & 0xff:02x}" for i in range(6))


def main():
    print("=== Fed-Watcher First-Time Setup ===\n")

    mac = get_mac()
    print(f"Detected MAC: {mac}")

    jwt_secret = secrets.token_hex(32)
    print(f"Generated JWT secret: {jwt_secret[:8]}...")

    password = getpass.getpass("Set admin password: ")
    confirm  = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        return

    hashed = pwd_ctx.hash(password)

    anthropic_key = input("Anthropic API key (sk-ant-...): ").strip()

    # Update .env
    env_text = ENV_FILE.read_text(encoding="utf-8")
    replacements = {
        "ANTHROPIC_API_KEY=":    f"ANTHROPIC_API_KEY={anthropic_key}",
        "JWT_SECRET=":           f"JWT_SECRET={jwt_secret}",
        "ADMIN_PASSWORD_HASH=":  f"ADMIN_PASSWORD_HASH={hashed}",
        "OWNER_MAC=":            f"OWNER_MAC={mac}",
    }
    for key, replacement in replacements.items():
        lines = env_text.split("\n")
        env_text = "\n".join(
            replacement if line.startswith(key) else line
            for line in lines
        )

    ENV_FILE.write_text(env_text, encoding="utf-8")
    print("\n.env updated successfully.")
    print("Run: uvicorn backend.main:app --host 0.0.0.0 --port 8000")


if __name__ == "__main__":
    main()
