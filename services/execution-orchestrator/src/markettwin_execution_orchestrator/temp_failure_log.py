"""Opt-in local diagnostics; normal worker failures use structured safe logs.

Writes under the ignored .local directory. Exception text is kept so a ValueError
can be read after the terminal is gone. Enable only for local diagnosis with
MARKETTWIN_TEMP_FAILURE_LOG_ENABLED=true. Credential-shaped values are redacted;
arbitrary application text is suitable only for a deliberately enabled local log.
"""

import logging
import os
import re
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_RUN_ID: ContextVar[str | None] = ContextVar("markettwin_temp_run_id", default=None)
_SECRET = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|password|secret|token)\s*[:=]\s*\S+"
    r"|sk-[A-Za-z0-9_-]{8,}"
    r"|Bearer\s+\S+"
)


def temp_log_path() -> Path:
    override = os.environ.get("MARKETTWIN_TEMP_FAILURE_LOG")
    if override:
        return Path(override)
    return Path.cwd() / ".local" / "temp-execution.log"


def bind_temp_run(test_run_id: object) -> object:
    return _RUN_ID.set(str(test_run_id))


def reset_temp_run(token: object) -> None:
    _RUN_ID.reset(token)  # type: ignore[arg-type]


def redact(text: str) -> str:
    return _SECRET.sub("[redacted]", text)


def record_temp_note(*, stage: str, detail: str) -> None:
    _append(
        "\n".join(
            (
                f"time={datetime.now(UTC).isoformat()}",
                f"stage={stage}",
                f"test_run_id={_RUN_ID.get() or '-'}",
                f"detail={redact(detail)[:2000]}",
                "",
            )
        )
    )


def record_temp_failure(*, stage: str, error: BaseException) -> None:
    """Append the exception chain immediately. Logging must not raise."""
    lines = [
        f"time={datetime.now(UTC).isoformat()}",
        f"stage={stage}",
        f"test_run_id={_RUN_ID.get() or '-'}",
    ]
    current: BaseException | None = error
    depth = 0
    while current is not None and depth < 5:
        message = redact(str(current)).replace("\r", " ")
        first = message.split("\n", 1)[0][:2000]
        lines.append(f"error_type={type(current).__name__}")
        lines.append(f"message={first}")
        frames = traceback.extract_tb(current.__traceback__)
        for frame in frames[-25:]:
            lines.append(f"at={frame.filename}:{frame.lineno} {frame.name}")
        cause = current.__cause__
        if cause is None and current.__context__ is not None and not current.__suppress_context__:
            cause = current.__context__
        current = cause
        depth += 1
        if current is not None:
            lines.append("caused_by")
    lines.append("")
    _append("\n".join(lines))


def _append(text: str) -> None:
    # Explicit diagnostic calls only: never copy arbitrary root logger content.
    if os.environ.get("MARKETTWIN_TEMP_FAILURE_LOG_ENABLED") != "true":
        return
    try:
        path = temp_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        try:
            handler.emit(logging.LogRecord(__name__, logging.INFO, "", 0, text, (), None))
        finally:
            handler.close()
    except Exception:
        logging.getLogger(__name__).warning("Temporary failure log could not be written")
