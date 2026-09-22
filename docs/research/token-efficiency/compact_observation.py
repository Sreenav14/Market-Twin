"""Reversible observation codec for offline evaluation; not enabled in the app."""

from collections.abc import Awaitable, Callable
from copy import deepcopy

SCHEMA = "markettwin.elements.v1"
COLUMNS = ("role", "name", "tag", "enabled", "level", "x", "y", "width", "height")
ELEMENT_KEYS = {"role", "name", "tag", "enabled", "level", "bounding_box"}
BOX_KEYS = {"x", "y", "width", "height"}
LEGEND = (
    "\nObservation encoding: visible_elements can be a table with schema, columns, and rows. "
    "Read each row using columns; x, y, width, height form bounding_box. "
    "All original element values and their order are preserved."
)


def pack(payload: dict) -> dict:
    """Preserve everything; leave unknown element schemas untouched."""
    result = deepcopy(payload)
    scene = result.get("observation")
    if not isinstance(scene, dict):
        return result
    elements = scene.get("visible_elements")
    if not isinstance(elements, (list, tuple)) or not elements:
        return result
    for element in elements:
        if not isinstance(element, dict) or set(element) != ELEMENT_KEYS:
            return result
        box = element["bounding_box"]
        if not isinstance(box, dict) or set(box) != BOX_KEYS:
            return result
    scene["visible_elements"] = {
        "schema": SCHEMA,
        "columns": list(COLUMNS),
        "rows": [
            [element[key] for key in COLUMNS[:5]]
            + [element["bounding_box"][key] for key in COLUMNS[5:]]
            for element in elements
        ],
    }
    return result


def unpack(payload: dict) -> dict:
    """Decode the exact supported schema, rejecting malformed encoded rows."""
    result = deepcopy(payload)
    scene = result.get("observation")
    if not isinstance(scene, dict):
        return result
    table = scene.get("visible_elements")
    if not isinstance(table, dict) or table.get("schema") != SCHEMA:
        return result
    if set(table) != {"schema", "columns", "rows"} or table["columns"] != list(COLUMNS):
        raise ValueError("Unexpected compact element schema")
    elements = []
    for row in table["rows"]:
        if not isinstance(row, list) or len(row) != len(COLUMNS):
            raise ValueError("Malformed compact element row")
        element = dict(zip(COLUMNS, row, strict=True))
        element["bounding_box"] = {key: element.pop(key) for key in COLUMNS[5:]}
        elements.append(element)
    scene["visible_elements"] = elements
    return result


def compile_request(callback_context, llm_request) -> None:
    """ADK callback reference: transform copies, never mutate stored events."""
    del callback_context
    contents = [content.model_copy(deep=True) for content in llm_request.contents]
    changed = False
    for content in contents:
        for part in content.parts or []:
            if part.function_response:
                response = part.function_response.response
                if isinstance(response, dict):
                    encoded = pack(response)
                    changed |= encoded != response
                    part.function_response.response = encoded
    llm_request.contents = contents
    if changed:
        instruction = llm_request.config.system_instruction
        if not isinstance(instruction, str):
            raise ValueError("Reference callback requires a string system instruction")
        if LEGEND not in instruction:
            llm_request.config.system_instruction = instruction + LEGEND


def make_compiler(measure_request: Callable[..., Awaitable[int]]):
    """Keep the original if the whole candidate request is not smaller.

    The injected measurement must be deterministic, local, and use the same
    serialization/tokenizer for both requests. It is not a provider billing API.
    """
    async def guarded_compile(callback_context, llm_request) -> None:
        original_contents = llm_request.contents
        original_config = llm_request.config.model_copy(deep=True)
        before = await measure_request(llm_request)
        try:
            compile_request(callback_context, llm_request)
            after = await measure_request(llm_request)
        except Exception:
            llm_request.contents = original_contents
            llm_request.config = original_config
            raise
        if after >= before:
            llm_request.contents = original_contents
            llm_request.config = original_config
    return guarded_compile
