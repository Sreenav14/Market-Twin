"""Reproducible synthetic serialization probe. No network or model calls.

Run from the repository root with .venv/Scripts/python.exe followed by this path.
This measures text tokenization, not provider billing or agent accuracy.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / ".venv/Lib/site-packages/litellm/litellm_core_utils/tokenizers"
os.environ["TIKTOKEN_CACHE_DIR"] = str(CACHE)

import tiktoken  # noqa: E402
import tiktoken.load  # noqa: E402


def reject_download(path: str) -> bytes:
    raise RuntimeError(f"Offline probe requires an existing tokenizer cache: {path}")


tiktoken.load.read_file = reject_download
encoder = tiktoken.get_encoding("o200k_base")

# Load only the dataclasses; do not initialize the app or an API client.
contract_path = ROOT / (
    "services/execution-orchestrator/src/"
    "markettwin_execution_orchestrator/browser/contracts.py"
)
spec = importlib.util.spec_from_file_location("probe_contracts", contract_path)
assert spec is not None and spec.loader is not None
contracts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = contracts
spec.loader.exec_module(contracts)

names = [
    "Software testing", "Search Wikipedia", "Search", "Contents",
    "Introduction", "Testing methods", "Test automation", "References",
]
elements = tuple(
    contracts.VisibleElement(
        role="heading" if i == 0 else "link",
        name=f"{names[i % len(names)]} {i}",
        tag="h1" if i == 0 else "a",
        enabled=True,
        level=1 if i == 0 else None,
        bounding_box=contracts.ElementBoundingBox(
            x=100 + (i % 4) * 220, y=60 + (i // 4) * 38, width=190, height=24
        ),
    )
    for i in range(80)
)
observation = contracts.BrowserObservation(
    url="https://example.com/software-testing",
    title="Software testing",
    aria_snapshot="\n".join(f'- link "{e.name}"' for e in elements),
    viewport_width=1280,
    viewport_height=900,
    scroll_y=0,
    document_height=12000,
    visible_elements=elements,
    accessibility_snapshot_path="artifacts/synthetic/action-0001-accessibility.yml",
    screenshot_path="artifacts/synthetic/action-0001-viewport.png",
    action_number=1,
)
baseline = contracts.BrowserActionResult("navigate", observation).to_dict()
baseline["step_id"] = 1
raw_scene = baseline["observation"]
columns = ["role", "name", "tag", "enabled", "level", "x", "y", "width", "height"]
rows = [
    [e.role, e.name, e.tag, e.enabled, e.level,
     e.bounding_box.x, e.bounding_box.y, e.bounding_box.width, e.bounding_box.height]
    for e in elements
]
table_scene = {k: v for k, v in raw_scene.items() if k != "visible_elements"}
table_scene["element_columns"] = columns
table_scene["element_rows"] = rows
table_payload = {"action": "navigate", "step_id": 1, "observation": table_scene}

# Confirm this first transformation is reversible on the synthetic fixture.
decoded = []
for row in rows:
    obj = dict(zip(columns, row, strict=True))
    obj["bounding_box"] = {key: obj.pop(key) for key in ("x", "y", "width", "height")}
    decoded.append(obj)
assert tuple(decoded) == raw_scene["visible_elements"]

# A deliberately lossy candidate: deployment requires retrieval/coverage evals.
small_scene = dict(table_scene)
small_scene.pop("aria_snapshot")
small_scene["element_rows"] = rows[:20]
small_scene["omitted_element_count"] = 60
small_scene["expansion_available"] = True
small_payload = {"action": "navigate", "step_id": 1, "observation": small_scene}


def count(value: object, *, compact: bool = False) -> int:
    kwargs = {"separators": (",", ":")} if compact else {}
    return len(encoder.encode(json.dumps(value, ensure_ascii=False, **kwargs)))


tokens = {
    "current_serializer_80_elements": count(baseline),
    "same_data_minified_json": count(baseline, compact=True),
    "same_data_column_table_80_elements": count(table_payload),
    "lossy_20_element_table_no_aria": count(small_payload),
}
result = {
    "kind": "synthetic_fixture_not_a_live_MarketTwin_run",
    "tokenizer": "o200k_base",
    "scope": "Tool result text only; excludes tools, prompts, message framing, images and outputs",
    "fixture": {"elements": 80, "aria_chars": len(observation.aria_snapshot)},
    "tokens": tokens,
    "reduction_pct_vs_current": {
        key: round(100 * (1 - value / tokens["current_serializer_80_elements"]), 2)
        for key, value in tokens.items()
    },
    "round_trip_all_80_element_fields": "passed",
    "warning": "Fewer tokens does not establish equivalent agent decisions or finding recall.",
}
out = Path(__file__).with_name("offline-probe-results.json")
out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
