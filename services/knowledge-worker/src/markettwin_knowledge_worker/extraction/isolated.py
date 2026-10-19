"""Killable document parsing with bounded result transfer."""

import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from markettwin_knowledge_worker.extraction.contracts import (
    ExtractedEvidence,
    ExtractionIssue,
    ExtractionResult,
)

PARSER_TIMEOUT_SECONDS = 60
VIDEO_CLIP_TIMEOUT_SECONDS = 120
MAX_RESULT_BYTES = 16 * 1024 * 1024
_PARSER_SCRIPT = Path(__file__).with_name("parser_process.py")


async def _run_parser(path: Path, destination: Path, operation: str, *arguments: str) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(_PARSER_SCRIPT), str(path), str(destination), operation, *arguments,
        stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL, start_new_session=os.name == "posix",
    )
    try:
        timeout = VIDEO_CLIP_TIMEOUT_SECONDS if operation == "clip" else PARSER_TIMEOUT_SECONDS
        async with asyncio.timeout(timeout):
            await process.wait()
        if process.returncode != 0:
            raise ValueError("Source parsing failed or exceeded its resource limit.")
    finally:
        if os.name == "posix":
            # Also reap native helper descendants if the wrapper crashed or
            # was cancelled. On Windows KILL_ON_JOB_CLOSE owns this boundary.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif process.returncode is None:
            process.kill()
        await process.wait()


async def extract_document(path: Path) -> ExtractionResult:
    """Always reap the parser before removing its source/result or releasing capacity."""
    with TemporaryDirectory(prefix="markettwin-parser-") as directory:
        result_path = Path(directory) / "result.json"
        await _run_parser(path, result_path, "document")
        if result_path.stat().st_size > MAX_RESULT_BYTES:
            raise ValueError("Document extraction result is too large.")
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        return ExtractionResult(
            source_path=path,
            units=tuple(ExtractedEvidence(**unit) for unit in payload["units"]),
            issues=tuple(ExtractionIssue(**issue) for issue in payload["issues"]),
            source_item_count=payload["source_item_count"],
            processed_item_count=payload["processed_item_count"],
        )


async def probe_video_duration(path: Path) -> float:
    with TemporaryDirectory(prefix="markettwin-probe-") as directory:
        result = Path(directory) / "duration.json"
        await _run_parser(path, result, "duration")
        if result.stat().st_size > 1024:
            raise ValueError("Invalid video duration result.")
        return float(json.loads(result.read_text(encoding="utf-8")))


async def trim_video(
    ffmpeg: str, source: Path, output: Path, start_seconds: float, end_seconds: float,
) -> None:
    await _run_parser(source, output, "clip", ffmpeg, str(start_seconds), str(end_seconds))
