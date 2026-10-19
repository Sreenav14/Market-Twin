"""Isolated architectural counterexamples; no SAM/product imports or network.

Run with an existing Python. Databases live in a temporary audit subdirectory.
These demonstrate mechanisms, not production correctness or throughput.
"""
import concurrent.futures
import json
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
import threading
from contextlib import closing
from pathlib import Path


def connect(path):
    db = sqlite3.connect(path, timeout=15, isolation_level=None)
    db.execute("PRAGMA busy_timeout=15000")
    return db


def child_write(path, deduplicate):
    with closing(connect(path)) as db:
        if deduplicate:
            db.execute("INSERT OR IGNORE INTO effects(operation) VALUES ('op-1')")
        else:
            db.execute("INSERT INTO effects(operation) VALUES ('op-1')")
    # The remote-like effect is committed, but no local receipt is persisted.
    os._exit(23)


def crash_case(root, deduplicate):
    path = root / ("dedup.db" if deduplicate else "naive.db")
    with closing(connect(path)) as db:
        unique = " UNIQUE" if deduplicate else ""
        db.execute("CREATE TABLE effects(operation TEXT" + unique + ")")
        db.execute("CREATE TABLE receipts(operation TEXT UNIQUE)")
    run = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "child", str(path),
         "1" if deduplicate else "0"], check=False, timeout=20,
        capture_output=True, text=True,
    )
    if run.returncode != 23:
        raise RuntimeError(f"Unexpected child exit: {run.returncode}")
    with closing(connect(path)) as db:
        before = db.execute("SELECT count(*) FROM effects").fetchone()[0]
        receipts = db.execute("SELECT count(*) FROM receipts").fetchone()[0]
        # Replay the same logical operation after the deliberately lost receipt.
        sql = "INSERT OR IGNORE" if deduplicate else "INSERT"
        db.execute(sql + " INTO effects(operation) VALUES ('op-1')")
        db.execute("INSERT INTO receipts(operation) VALUES ('op-1')")
        after = db.execute("SELECT count(*) FROM effects").fetchone()[0]
    assert (before, receipts, after) == (1, 0, 1 if deduplicate else 2)
    return {"child_exit": run.returncode, "effects_before_replay": before,
            "receipts_before_replay": receipts, "effects_after_replay": after}


def budget_case(root, atomic, index):
    path = root / f"budget-{atomic}-{index}.db"
    with closing(connect(path)) as db:
        db.execute("CREATE TABLE budget(id INTEGER PRIMARY KEY, remaining INTEGER)")
        db.execute("INSERT INTO budget VALUES(1, 100)")
        db.execute("CREATE TABLE reservations(worker INTEGER PRIMARY KEY, amount INTEGER)")
    gate = threading.Barrier(8, timeout=15)

    def reserve(worker):
        db = connect(path)
        try:
            if atomic:
                gate.wait()
                db.execute("BEGIN IMMEDIATE")
                changed = db.execute(
                    "UPDATE budget SET remaining=remaining-30 "
                    "WHERE id=1 AND remaining>=30"
                ).rowcount
            else:
                observed = db.execute("SELECT remaining FROM budget").fetchone()[0]
                gate.wait()  # Force all eight readers to observe the original balance.
                changed = int(observed >= 30)
                if changed:
                    db.execute("UPDATE budget SET remaining=remaining-30 WHERE id=1")
            if changed:
                db.execute("INSERT INTO reservations VALUES (?, 30)", (worker,))
            db.commit()
            return changed
        finally:
            db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        accepted = sum(pool.map(reserve, range(8)))
    with closing(connect(path)) as db:
        remaining = db.execute("SELECT remaining FROM budget").fetchone()[0]
        reserved = db.execute("SELECT coalesce(sum(amount),0) FROM reservations").fetchone()[0]
    assert (accepted, remaining, reserved) == ((3, 10, 90) if atomic else (8, -140, 240))
    return {"accepted": accepted, "remaining_units": remaining, "reserved_units": reserved}


def main():
    audit_root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="scratch-", dir=audit_root) as temp:
        root = Path(temp)
        assert root.resolve().parent == audit_root
        result = {
            "scope": "stdlib/SQLite mechanism tests, not SAM or PostgreSQL validation",
            "python": platform.python_version(), "os": platform.system(),
            "crash_without_provider_dedup": crash_case(root, False),
            "crash_with_provider_dedup": crash_case(root, True),
            "budget_without_atomic_admission": [budget_case(root, False, i) for i in range(10)],
            "budget_with_atomic_admission": [budget_case(root, True, i) for i in range(10)],
        }
    # Analytical scenarios, not runtime or performance benchmarks.
    result["cost_scenarios"] = [
        {"name": name, "tasks_per_month": tasks,
         "input_mtokens": tasks * inp / 1_000_000,
         "output_mtokens": tasks * out / 1_000_000,
         "text_usd": round(tasks * (inp * 2.5 + out * 15) / 1_000_000, 2)}
        for name, tasks, inp, out in [
            ("low", 60, 25_000, 4_000),
            ("medium", 300, 80_000, 12_000),
            ("high", 900, 250_000, 35_000),
        ]
    ]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child_write(sys.argv[2], sys.argv[3] == "1")
    else:
        main()
