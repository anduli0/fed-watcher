"""
Async wrapper around `claude -p` CLI for LLM calls without a direct API key.
Uses the Claude Code CLI that is already authenticated in this environment.
"""
import asyncio
import json
import os
import shutil
import tempfile
from typing import Optional

CLAUDE_BIN: str = shutil.which("claude") or "claude"

# Each `claude -p` invocation is a full Claude Code (Node.js) process using
# several hundred MB of RAM. On memory-constrained hosts (e.g. Render free tier
# = 512 MB) running several at once triggers the OOM killer. Default to fully
# serialized calls; raise via CLAUDE_MAX_CONCURRENT on a larger instance.
MAX_CONCURRENT: int = int(os.getenv("CLAUDE_MAX_CONCURRENT", "1"))

# Cap each claude process's V8 heap so a single call can't balloon past the
# container limit. Tunable via CLAUDE_NODE_MAX_OLD_SPACE_MB (MB).
_NODE_HEAP_MB: str = os.getenv("CLAUDE_NODE_MAX_OLD_SPACE_MB", "320")

_semaphore: Optional[asyncio.Semaphore] = None


def _sem() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore


async def call_claude(system_prompt: str, user_message: str, timeout: float = 120.0) -> str:
    """
    Call Claude via CLI in non-interactive print mode.
    Passes system_prompt via --system-prompt, user_message via stdin.
    Returns the raw text result string.
    """
    async with _sem():
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

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"claude CLI exited {proc.returncode}: {err}")

        raw = stdout.decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"claude CLI JSON parse error: {exc}. Raw: {raw[:300]}")

        if data.get("is_error"):
            raise RuntimeError(f"claude CLI error: {data.get('result', '')[:300]}")

        return data.get("result", "")
