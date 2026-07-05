"""
Async wrapper around `claude -p` CLI for LLM calls without a direct API key.
Uses the Claude Code CLI that is already authenticated in this environment.
"""
import asyncio
import json
import logging
import os
import shutil
import tempfile
from typing import Optional

logger = logging.getLogger("fed_watcher.claude_cli")

CLAUDE_BIN: str = shutil.which("claude") or "claude"


class ClaudeAuthError(RuntimeError):
    """The claude CLI ran but could not authenticate (HTTP 401/403).

    This is NOT a transient failure — retrying with the same (missing/expired)
    credentials will always fail, so it is raised separately so callers can
    fail fast instead of burning the retry budget. The fix is operational:
    provide a valid credential to the environment (see ``auth_mode``).
    """


# Candidate credential file locations the bundled `claude` CLI reads.
_CRED_FILES = (
    "/root/.claude/.credentials.json",
    os.path.expanduser("~/.claude/.credentials.json"),
)


def auth_mode() -> str:
    """Describe which credential the child `claude` process will *likely* use.

    Diagnostic only — the managed Claude Code harness can also inject auth with
    none of these present, so a return of ``"none"`` does not prove auth is
    unavailable. Use :func:`verify_auth` for the authoritative answer.
    """
    if os.getenv("CLAUDE_CODE_OAUTH_TOKEN"):
        return "oauth_token (CLAUDE_CODE_OAUTH_TOKEN)"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "api_key (ANTHROPIC_API_KEY)"
    for p in _CRED_FILES:
        if os.path.exists(p):
            return f"credentials_file ({p})"
    return "none"

# Each `claude -p` invocation is a full Claude Code (Node.js) process using
# several hundred MB of RAM. On memory-constrained hosts (e.g. Render free tier
# = 512 MB) running several at once triggers the OOM killer. Default to fully
# serialized calls; raise via CLAUDE_MAX_CONCURRENT on a larger instance.
MAX_CONCURRENT: int = int(os.getenv("CLAUDE_MAX_CONCURRENT", "1"))

# Cap each claude process's V8 heap. Too low and the CLI itself crashes (exit 1
# with no output); too high (× concurrency) and the container OOMs. With
# concurrency=1 on a 512 MB host, ~256 MB leaves room for the Python app.
# Tunable via CLAUDE_NODE_MAX_OLD_SPACE_MB (MB).
_NODE_HEAP_MB: str = os.getenv("CLAUDE_NODE_MAX_OLD_SPACE_MB", "256")

# Retry transient failures (exit 1 with no output, timeouts) — these happen
# under memory pressure or brief rate limiting when many agents run in sequence.
_MAX_RETRIES: int = int(os.getenv("CLAUDE_MAX_RETRIES", "2"))
_RETRY_BASE_DELAY: float = float(os.getenv("CLAUDE_RETRY_DELAY", "3.0"))

# Default per-call timeout for agent/report calls. Small, throttled hosts (e.g.
# Render free tier) run `claude -p` much slower than a dev box, so be generous.
# Tunable via CLAUDE_CALL_TIMEOUT (seconds).
_CALL_TIMEOUT: float = float(os.getenv("CLAUDE_CALL_TIMEOUT", "240"))

# Auth-probe timeout. The FIRST `claude -p` call on a cold, memory-constrained
# host does one-time Node/CLI init and can take far longer than a warm call, so
# allow generous time before calling the probe a transient failure.
# Tunable via CLAUDE_AUTH_PROBE_TIMEOUT (seconds).
_AUTH_PROBE_TIMEOUT: float = float(os.getenv("CLAUDE_AUTH_PROBE_TIMEOUT", "180"))

_semaphore: Optional[asyncio.Semaphore] = None

# Cached result of the most recent verify_auth() ping so /health and the cycle
# gate can read auth status without spawning a fresh claude process every time.
_last_auth_ok: Optional[bool] = None
_last_auth_detail: str = "not checked yet"


def last_auth_status() -> tuple[Optional[bool], str]:
    """(ok, detail) from the most recent verify_auth() call. ok=None = unchecked."""
    return _last_auth_ok, _last_auth_detail


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


async def _run_once(system_prompt: str, user_message: str, timeout: float) -> str:
    """Single `claude -p` invocation. Raises RuntimeError on any failure."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(system_prompt)
        sp_file = f.name

    # Constrain the child claude process's Node heap to avoid OOM kills.
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
            cwd="/tmp",  # run outside git repo so stop-hook exits early
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

    # IMPORTANT: `claude -p --output-format json` can exit non-zero (e.g. 1) even
    # when the request fully succeeded — a Stop hook or post-response cleanup step
    # in the CLI returns a non-zero code while a valid result JSON is already on
    # stdout. So parse stdout FIRST and trust a well-formed, non-error result
    # regardless of the process exit code. Only fall back to treating the exit
    # code as a failure when there is no usable result.
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
        # Parsed but no result text and not a success — treat as failure below.

    detail = (err.strip() or raw.strip() or "(no output on stdout/stderr)")[:500]
    raise RuntimeError(f"claude CLI exited {proc.returncode}: {detail}")


async def call_claude(system_prompt: str, user_message: str, timeout: Optional[float] = None) -> str:
    """
    Call Claude via CLI in non-interactive print mode.
    Passes system_prompt via --system-prompt-file, user_message via stdin.
    Retries transient failures with exponential backoff. Returns the result text.
    """
    if timeout is None:
        timeout = _CALL_TIMEOUT
    async with _sem():
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await _run_once(system_prompt, user_message, timeout)
            except ClaudeAuthError:
                # Bad/expired/missing credentials never recover by retrying —
                # surface immediately so the caller can fail the whole cycle fast.
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
    """Single tiny `claude -p` ping used as a cycle preflight.

    Returns ``(ok, detail)``. ``ok`` is False ONLY on a *definitive* auth failure
    (HTTP 401/403) — that is the case worth aborting a 21-agent cycle for. A
    transient failure (slow cold start on a throttled host, timeout, OOM) returns
    ``ok=True`` with a TRANSIENT detail: the real work has its own retries and
    longer timeouts, so a merely-slow host must NOT be permanently blocked from
    ever running a cycle. ``detail`` always records what actually happened.
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
        # The one case we hard-block on: credentials are missing/invalid.
        _last_auth_ok, _last_auth_detail = False, f"AUTH: {e}"
    except Exception as e:  # timeout / OOM / cold-start slowness — not an auth failure
        _last_auth_ok, _last_auth_detail = True, f"TRANSIENT(allowed): {str(e)[:160]}"
    return _last_auth_ok, _last_auth_detail
