"""Restart the execution process after an unexpected exit; Ctrl+C stops supervision."""

import logging
import os
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

CHILD_ENV = "MARKETTWIN_EXECUTION_CHILD"


def supervise(*, popen=subprocess.Popen, sleep=time.sleep, clock=time.monotonic):
    log = logging.getLogger("markettwin.execution.supervisor")
    log.setLevel(logging.INFO)
    directory = Path.cwd() / ".local"
    directory.mkdir(exist_ok=True)
    handler = RotatingFileHandler(directory / "execution-supervisor.log",
                                  maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    log.addHandler(handler)
    delay = 1
    child = None
    try:
        while True:
            started = clock()
            child = popen([sys.executable, "-m", "markettwin_execution_orchestrator.worker"],
                env={**os.environ, CHILD_ENV: "1"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            log.info("Worker started pid=%s", child.pid)
            code = child.wait()
            log.error("Worker exited code=%s; restarting", code)
            delay = 1 if clock() - started >= 60 else min(delay * 2, 60)
            sleep(delay)
    except KeyboardInterrupt:
        log.info("Supervisor stopped by operator")
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        log.removeHandler(handler)
        handler.close()
