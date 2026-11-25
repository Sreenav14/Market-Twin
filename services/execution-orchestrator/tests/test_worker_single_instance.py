"""The worker's single-instance guard, proven with real subprocesses.

An OS file lock is held per process, so an in-process double-lock check
cannot prove the guard: each scenario runs acquire_worker_lock() in a
child python and observes its exit code and stderr. The lock path is
injected via MARKETTWIN_WORKER_LOCK_FILE so tests never touch the real
worker lock.
"""

import os
import subprocess
import sys

CHILD_PROGRAM = """
import os
import time

from markettwin_execution_orchestrator.worker import acquire_worker_lock

handle = acquire_worker_lock()
if handle is None:
    raise SystemExit(3)
print(f"ACQUIRED {os.getpid()}", flush=True)
if os.environ.get("WORKER_LOCK_HOLD") == "1":
    deadline = time.time() + 120
    release = os.environ["WORKER_LOCK_RELEASE"]
    while time.time() < deadline and not os.path.exists(release):
        time.sleep(0.05)
"""


def _spawn_guard(lock_path, *, hold=False, release_path=None):
    env = {**os.environ, "MARKETTWIN_WORKER_LOCK_FILE": str(lock_path)}
    if hold:
        env["WORKER_LOCK_HOLD"] = "1"
        env["WORKER_LOCK_RELEASE"] = str(release_path)
    return subprocess.Popen(
        [sys.executable, "-c", CHILD_PROGRAM],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_second_worker_is_refused_while_first_holds_the_lock(tmp_path):
    lock_path = tmp_path / "worker.lock"
    release_path = tmp_path / "release"
    holder = _spawn_guard(lock_path, hold=True, release_path=release_path)
    try:
        acquired = holder.stdout.readline()
        assert acquired.startswith("ACQUIRED")
        holder_pid = acquired.split()[1]
        contender = _spawn_guard(lock_path)
        _, stderr = contender.communicate(timeout=180)
        assert contender.returncode == 3
        assert "already running" in stderr
        assert holder_pid in stderr
    finally:
        release_path.touch()
        try:
            holder.wait(timeout=180)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait(timeout=30)


def test_worker_lock_is_acquired_when_nobody_holds_it(tmp_path):
    child = _spawn_guard(tmp_path / "worker.lock")
    stdout, _ = child.communicate(timeout=180)
    assert child.returncode == 0
    assert stdout.startswith("ACQUIRED")
