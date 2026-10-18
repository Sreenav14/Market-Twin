"""Bounded rerun configuration shared by the API and execution runtime."""

import math
import re
from typing import cast

BROWSER_TOOLS = (
    "browser_get_state",
    "browser_navigate",
    "browser_click",
    "browser_fill",
    "browser_select",
    "browser_scroll",
    "browser_go_back",
    "browser_wait",
    "browser_capture_element",
    "browser_take_screenshot",
    "browser_get_form_state",
    "browser_focus_next",
    "browser_set_viewport",
    "browser_check",
    "browser_uncheck",
)
DEFAULT_TEMPERATURE = 0.05


def default_configuration(name: str, tools: tuple[str, ...] = ()) -> dict[str, object]:
    return {
        "name": name,
        "agent_type": "LlmAgent",
        "temperature": DEFAULT_TEMPERATURE,
        "tools": list(tools),
        "sub_agents": [],
    }


def validate_configuration(value: object, *, browser_allowed: bool) -> dict[str, object]:
    """Only one sequential level and registered, journey-scoped tools are supported."""
    names: set[str] = set()

    def node(raw: object, *, child: bool = False) -> dict[str, object]:
        if not isinstance(raw, dict):
            raise ValueError("Agent configuration must be an object.")
        fields = {"name", "agent_type", "temperature", "tools", "sub_agents"}
        if child:
            fields.add("instruction")
        data = cast(dict[str, object], raw)
        if set(data) != fields:
            raise ValueError(
                "Keep the required agent configuration fields; unknown fields are rejected."
            )
        name = data["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name):
            raise ValueError(
                "Agent names must start with a letter or underscore and contain "
                "at most 64 letters, digits or underscores."
            )
        if name in names:
            raise ValueError("Every agent and sequential parent must have a unique name.")
        names.add(name)
        kind = data["agent_type"]
        if kind not in ("LlmAgent", "SequentialAgent") or (child and kind != "LlmAgent"):
            raise ValueError("Choose LlmAgent or SequentialAgent; subagents must be LlmAgent.")
        temperature = data["temperature"]
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, (float, int))
            or not math.isfinite(temperature)
            or not 0 <= temperature <= 0.2
        ):
            raise ValueError("Temperature must be between 0 and 0.2.")
        tools_value = data["tools"]
        if not isinstance(tools_value, list):
            raise ValueError("Tools must be a list.")
        tools = cast(list[object], tools_value)
        allowed = BROWSER_TOOLS if browser_allowed else ()
        if any(not isinstance(tool, str) or tool not in allowed for tool in tools) or len(
            set(tools)
        ) != len(tools):
            raise ValueError("Select unique tools from this agent's approved tool registry.")
        children_value = data["sub_agents"]
        if not isinstance(children_value, list):
            raise ValueError("Subagents must be a list.")
        children = cast(list[object], children_value)
        if len(children) > 3 or (kind == "LlmAgent" and children):
            raise ValueError(
                "Only SequentialAgent can contain subagents, "
                "with at most three additional LLM agents."
            )
        result = {
            **data,
            "temperature": float(temperature),
            "sub_agents": [node(item, child=True) for item in children],
        }
        if child:
            instruction = data["instruction"]
            if (
                not isinstance(instruction, str)
                or not instruction.strip()
                or len(instruction) > 6000
            ):
                raise ValueError(
                    "Each additional agent needs an instruction of 1–6,000 characters."
                )
        # The final structured reporter is a real child, with its own unique name.
        if kind == "SequentialAgent":
            reporter = f"{name}_reporter"
            if len(reporter) > 64 or reporter in names:
                raise ValueError(
                    "Reserve a unique parent_name_reporter name; "
                    "sequential parent names must be at most 55 characters."
                )
        return result

    return node(value)
