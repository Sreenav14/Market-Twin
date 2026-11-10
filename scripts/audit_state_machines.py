"""Index state-machine evidence without importing or executing application code.

Run from any directory with Python; --check detects a stale committed inventory.
This is a candidate index, not proof that every semantic machine was identified.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/state-machine-inventory.json"
PATTERNS = {
    "react_state": re.compile(r"\buse(?:State|Reducer)\b"),
    "state_field": re.compile(
        r"\b(?:\w*(?:status|state|stage|phase|control_mode)|generation|dispatch_state)\b"
        r"\s*(?::|=|\bin\b|\bnot\s+in\b|[!=]=)"
    ),
    "recovery_clock": re.compile(
        r"\b(?:\w*(?:expires_at|quarantined_at|next_attempt_at)|refetchInterval|"
        r"setTimeout|setInterval|retry|resume_count|evaluation_attempts|published_at|"
        r"revoked_at|consumed_at|released_at)\b"
    ),
}


def inventory() -> dict[str, object]:
    files = []
    for parent in ("apps", "packages", "services"):
        for source in (ROOT / parent).glob("*/src/**/*"):
            if source.suffix not in {".py", ".ts", ".tsx"}:
                continue
            if any(part in {"__pycache__", "node_modules", "dist"} for part in source.parts):
                continue
            if ".test." in source.name or ".spec." in source.name:
                continue
            files.append(source)
    candidates = []
    database_domains = []
    for source in sorted(files):
        path = source.relative_to(ROOT).as_posix()
        content = source.read_text(encoding="utf-8-sig")
        evidence = []
        for number, line in enumerate(content.splitlines(), 1):
            if line.lstrip().startswith(("#", "//", "*")):
                continue
            kinds = [kind for kind, pattern in PATTERNS.items() if pattern.search(line)]
            if kinds:
                evidence.append({"line": number, "kinds": kinds, "source": line.strip()})
        if evidence:
            candidates.append({"path": path, "evidence": evidence})
        if path.startswith("packages/database-python/src/markettwin_database/models/"):
            tree = ast.parse(content, filename=path)
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                constraints = []
                for child in ast.walk(node):
                    if (isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                            and child.func.id == "CheckConstraint" and child.args
                            and isinstance(child.args[0], ast.Constant)
                            and isinstance(child.args[0].value, str)):
                        constraint = child.args[0].value
                        if re.search(
                            r"\b(?:status|state|control_mode|dispatch_state|phase)\b", constraint,
                        ):
                            constraints.append({"line": child.lineno, "constraint": constraint})
                if constraints:
                    database_domains.append({"model": node.name, "path": path,
                                             "constraints": constraints})
    return {
        "schema_version": 1,
        "scope": (
            "Application Python/TypeScript source under "
            "apps/*/src, packages/*/src, services/*/src"
        ),
        "limitations": [
            "Heuristic candidate index: flags, URLs, timestamps and external protocols "
            "can encode additional machines.",
            "Allowed database values are domains, not legal transition graphs.",
            "Read transition guards and transaction boundaries before changing behavior.",
            "Tests, migrations, scripts, styles and dependencies are excluded; "
            "examples remain labeled by source path.",
        ],
        "source_files_scanned": len(files),
        "database_domains": database_domains,
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = inventory()
    encoded = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != encoded:
            print("State-machine inventory is stale; run scripts/audit_state_machines.py")
            return 1
    else:
        OUTPUT.write_text(encoded, encoding="utf-8")
    print(f"Scanned {document['source_files_scanned']} source files; "
          f"indexed {len(document['database_domains'])} database state domains and "
          f"{len(document['candidates'])} candidate files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
