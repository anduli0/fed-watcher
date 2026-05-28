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
MAX_CONCURRENT: int = 4

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

        try:
            proc = await asyncio.create_subprocess_exec(
                CLAUDE_BIN, "-p",
                "--output-format", "json",
                "--system-prompt-file", sp_file,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/tmp",  # run outside git repo so stop-hook exits early
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
