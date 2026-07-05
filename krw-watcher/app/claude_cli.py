"""
Async wrapper around the `claude -p` CLI so the analysis engine runs on the
owner's Claude subscription (CLAUDE_CODE_OAUTH_TOKEN) instead of a metered API
key. Trimmed copy of fed-watcher's backend/claude_cli.py.
"""
import asyncio
import json
import logging
import os
import shutil
import tempfile
from typing import Optional

logger = logging.getLogger("krw_watcher.claude_cli")

CLAUDE_BIN: str = shutil.which("claude") or "claude"


class ClaudeAuthError(RuntimeError):
    """The claude CLI ran but could not authenticate (HTTP 401/403).

    Retrying with the same credentials always fails, so this is raised
    separately for fail-fast handling. Fix is operational: set
    CLAUDE_CODE_OAUTH_TOKEN (run `claude setup-token`) in the environment.
    """


_CRED_FILES = (
    "/root/.claude/.credentials.json",
    os.path.expanduser("~/.claude/.credentials.json"),
)


def auth_mode() -> str:
    if os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        return "oauth_token (CLAUDE_CODE_OAUTH_TOKEN)"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "api_key (ANTHROPIC_API_KEY)"
    for p in _CRED_FILES:
        if os.path.exists(p):
            return f"credentials_file ({p})"
    return "none"


# Each `claude -p` invocation is a full Node.js process using several hundred
# MB of RAM; on a 512 MB free-tier host run them one at a time with a capped
# V8 heap.
MAX_CONCURRENT: int = int(os.getenv("CLAUDE_MAX_CONCURRENT", "1"))
_NODE_HEAP_MB: str = os.getenv("CLAUDE_NODE_MAX_OLD_SPACE_MB", "256")
_MAX_RETRIES: int = int(os.getenv("CLAUDE_MAX_RETRIES", "2"))
_RETRY_BASE_DELAY: float = float(os.getenv("CLAUDE_RETRY_DELAY", "3.0"))

# Generous timeouts: the FIRST call on a cold, throttled host does one-time
# CLI init and runs far slower than a dev box.
_CALL_TIMEOUT: float = float(os.getenv("CLAUDE_CALL_TIMEOUT", "240"))
_AUTH_PROBE_TIMEOUT: float = float(os.getenv("CLAUDE_AUTH_PROBE_TIMEOUT", "180"))

_semaphore: Optional[asyncio.Semaphore] = None

_last_auth_ok: Optional[bool] = None
_last_auth_detail: str = "not checked yet"


def last_auth_status() -> tuple[Optional[bool], str]:
    return _last_auth_ok, _last_auth_detail


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


async def _run_once(system_prompt: str, user_message: str, timeout: float) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(system_prompt)
        sp_file = f.name

    child_env = dict(os.environ)
    existing_node_opts = child_env.get("NODE_OPTIONS", "")
    if "max-old-space-size" not in existing_node_opts:
        child_env["NODE_OPTIONS"] = (
            f"{existing_node_opts} --max-old-space-size={_NODE_HEAP_MB}".strip()
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            CLAUDE_BIN, "-p",
            "--output-format", "json",
            "--system-prompt-file", sp_file,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/tmp",  # outside any git repo so repo hooks don't interfere
            env=child_env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=user_message.encode("utf-8")),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"claude CLI timed out after {timeout}s")
    finally:
        try:
            os.unlink(sp_file)
        except OSError:
            pass

    raw = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")

    # `claude -p --output-format json` can exit non-zero even when the request
    # fully succeeded (post-response cleanup steps). Parse stdout FIRST and
    # trust a well-formed non-error result regardless of the exit code.
    data = None
    if raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None

    if data is not None:
        if data.get("is_error"):
            msg = str(data.get("result", ""))[:300]
            api_err = data.get("api_error_status")
            low = msg.lower()
            if api_err in (401, 403) or "authenticate" in low or "401" in low or "403" in low:
                raise ClaudeAuthError(
                    f"claude CLI auth failed (api_error_status={api_err}): {msg}"
                )
            raise RuntimeError(f"claude CLI error: {msg}")
        result = data.get("result", "")
        if result or data.get("subtype") == "success":
            return result

    detail = (err.strip() or raw.strip() or "(no output on stdout/stderr)")[:500]
    raise RuntimeError(f"claude CLI exited {proc.returncode}: {detail}")


async def call_claude(system_prompt: str, user_message: str,
                      timeout: Optional[float] = None) -> str:
    """Call Claude in non-interactive print mode with retries on transient errors."""
    if timeout is None:
        timeout = _CALL_TIMEOUT
    async with _sem():
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await _run_once(system_prompt, user_message, timeout)
            except ClaudeAuthError:
                raise
            except RuntimeError as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "claude CLI attempt %d/%d failed (%s); retrying in %.1fs",
                        attempt + 1, _MAX_RETRIES + 1, str(exc)[:200], delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "claude CLI failed after %d attempts: %s",
                        _MAX_RETRIES + 1, str(exc)[:300],
                    )
        assert last_exc is not None
        raise last_exc


async def verify_auth(timeout: Optional[float] = None) -> tuple[bool, str]:
    """Tiny `claude -p` ping used as a preflight.

    Returns ok=False ONLY on a definitive auth failure (401/403). Transient
    failures (cold start, timeout) return ok=True with a TRANSIENT detail so a
    merely-slow host is never permanently blocked from analysing.
    """
    global _last_auth_ok, _last_auth_detail
    if timeout is None:
        timeout = _AUTH_PROBE_TIMEOUT
    try:
        out = await _run_once(
            "You are a health probe. Reply with the single word: OK.",
            "ping",
            timeout,
        )
        _last_auth_ok, _last_auth_detail = True, (out.strip()[:60] or "ok")
    except ClaudeAuthError as e:
        _last_auth_ok, _last_auth_detail = False, f"AUTH: {e}"
    except Exception as e:
        _last_auth_ok, _last_auth_detail = True, f"TRANSIENT(allowed): {str(e)[:160]}"
    return _last_auth_ok, _last_auth_detail
