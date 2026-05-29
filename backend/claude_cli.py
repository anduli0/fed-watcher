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

_semaphore: Optional[asyncio.Semaphore] = None


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

    if proc.returncode != 0:
        # Surface both streams — claude sometimes emits diagnostics on stdout and
        # exits non-zero with an empty stderr (hard V8 abort / OOM look like this).
        detail = (err.strip() or raw.strip() or "(no output on stdout/stderr)")[:500]
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {detail}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"claude CLI JSON parse error: {exc}. Raw: {raw[:300]}")

    if data.get("is_error"):
        raise RuntimeError(f"claude CLI error: {data.get('result', '')[:300]}")

    return data.get("result", "")


async def call_claude(system_prompt: str, user_message: str, timeout: float = 120.0) -> str:
    """
    Call Claude via CLI in non-interactive print mode.
    Passes system_prompt via --system-prompt-file, user_message via stdin.
    Retries transient failures with exponential backoff. Returns the result text.
    """
    async with _sem():
        last_exc: Optional[Exception] = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return await _run_once(system_prompt, user_message, timeout)
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
