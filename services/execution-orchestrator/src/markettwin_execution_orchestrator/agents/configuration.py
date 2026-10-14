"""Build a real ADK agent tree without changing journey evidence ownership."""

import json
from typing import Any, cast

from google.adk.agents import (  # pyright: ignore[reportDeprecated]
    BaseAgent,
    LlmAgent,
    SequentialAgent,  # pyright: ignore[reportDeprecated]
)
from markettwin_shared.agent_configuration import default_configuration, validate_configuration

from markettwin_execution_orchestrator.models.model_factory import (
    create_model,
    resolve_model_runtime_configuration,
)


def configure_agent(
    agent: LlmAgent,
    override: dict[str, str] | None,
    *,
    name: str,
    max_tokens: int,
    browser_allowed: bool,
) -> tuple[BaseAgent, dict[str, object], dict[str, object]]:
    tool_objects = cast(list[Any], agent.tools)  # pyright: ignore[reportUnknownMemberType]
    available = {
        str(getattr(tool, "name", getattr(tool, "__name__", ""))): tool
        for tool in tool_objects
    }
    raw = (
        json.loads(override["agent_configuration"])
        if override and "agent_configuration" in override
        else default_configuration(name, tuple(available))
    )
    settings = validate_configuration(raw, browser_allowed=browser_allowed)

    def apply(llm: LlmAgent, config: dict[str, object], agent_name: str) -> dict[str, object]:
        temperature = cast(float, config["temperature"])
        llm.name = agent_name
        llm.model = create_model(max_tokens=max_tokens, temperature=temperature)
        llm.tools = [available[tool] for tool in cast(list[str], config["tools"])]
        return {
            "name": llm.name,
            "agent_type": "LlmAgent",
            "model_configuration": resolve_model_runtime_configuration(
                max_tokens=max_tokens, temperature=temperature
            ).snapshot_parameters(),
            "tools": list(cast(list[str], config["tools"])),
            "sub_agents": [],
            "instruction": llm.instruction,
        }

    children: list[BaseAgent] = []
    structure: list[dict[str, object]] = []
    for child in cast(list[dict[str, object]], settings["sub_agents"]):
        # Helpers inherit the same scope/evidence rules. Their output is context,
        # never independent proof or the final structured product report.
        helper = LlmAgent(
            name=cast(str, child["name"]),
            model=agent.model,
            instruction=(f"{agent.instruction}\n\nAdditional task:\n{child['instruction']}\n"
                         "Return observations as context. "
                         "Do not submit the final structured report."),
        )
        structure.append(apply(helper, child, helper.name))
        children.append(helper)
    parent_name = cast(str, settings["name"])
    primary_name = (
        parent_name if settings["agent_type"] == "LlmAgent" else f"{parent_name}_reporter"
    )
    primary = apply(agent, settings, primary_name)
    if settings["agent_type"] == "LlmAgent":
        primary["configuration"] = settings
        return agent, primary, primary
    children.append(agent)
    structure.append(primary)
    return (
        SequentialAgent(name=parent_name, sub_agents=children),  # pyright: ignore[reportDeprecated]
        {
            "name": parent_name,
            "agent_type": "SequentialAgent",
            "sub_agents": structure,
            "configuration": settings,
        },
        primary,
    )
