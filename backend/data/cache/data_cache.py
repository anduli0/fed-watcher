import json
import time
from pathlib import Path

CACHE_DIR = Path("C:/Users/andul/fed-watcher/.cache")
CACHE_DIR.mkdir(exist_ok=True)


def _path(key: str) -> Path:
    safe = key.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe}.json"


def get(key: str, ttl_seconds: int) -> dict | None:
    p = _path(key)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if time.time() - data["ts"] < ttl_seconds:
            return data["value"]
    except Exception:
        pass
    return None


def set(key: str, value: dict | list | str):
    _path(key).write_text(
        json.dumps({"ts": time.time(), "value": value}, ensure_ascii=False),
        encoding="utf-8",
    )
