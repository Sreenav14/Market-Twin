"""Exercise ADK's report tool without replaying browser actions or calling a model."""

from collections.abc import AsyncGenerator

import pytest
from google.adk.agents import LlmAgent
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types
from markettwin_execution_orchestrator.agents.schemas.persona_report import (
    CriterionEvidence,
    PersonaAgentReport,
)
from markettwin_execution_orchestrator.workflow.journey_executor import (
    _parse_persona_report,  # pyright: ignore[reportPrivateUsage]
)
from pydantic import Field, ValidationError


class ReportModel(BaseLlm):
    report: dict[str, object]
    available_tools: list[str] = Field(default_factory=list)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.available_tools.extend(llm_request.tools_dict)
        yield LlmResponse(content=types.Content(role="model", parts=[
            types.Part(function_call=types.FunctionCall(
                name="set_model_response", args=self.report,
            )),
        ]))


async def unused_browser_tool() -> dict[str, object]:
    raise AssertionError("Report submission must not replay browser actions.")


async def run_report(model: ReportModel) -> str:
    agent = LlmAgent(
        name="persona_report_test", model=model, instruction="Report observed evidence.",
        tools=[unused_browser_tool], output_schema=PersonaAgentReport,
    )
    runner = InMemoryRunner(agent=agent, app_name="persona_report_test")
    try:
        await runner.session_service.create_session(
            app_name="persona_report_test", user_id="test", session_id="report",
        )
        final: list[str] = []
        async for event in runner.run_async(
            user_id="test", session_id="report",
            new_message=types.Content(role="user", parts=[types.Part(text="Submit report.")]),
        ):
            if event.is_final_response() and event.content:
                final.extend(part.text for part in event.content.parts or [] if part.text)
        return "\n".join(final)
    finally:
        await runner.close()


async def test_adk_report_tool_serializes_quotes_and_preserves_criterion_status() -> None:
    report = PersonaAgentReport(
        outcome="passed", summary='Search returned "Artificial intelligence".\nResult opened.',
        criterion_evidence=(CriterionEvidence(
            criterion="Search result opens", status="satisfied", evidence_step_ids=(2,),
        ),),
    )
    model = ReportModel(model="openai/test-model", report=report.model_dump(mode="json"))
    result = _parse_persona_report(await run_report(model))
    assert result == report
    assert "set_model_response" in model.available_tools
    assert "unused_browser_tool" in model.available_tools


async def test_adk_report_tool_rejects_satisfied_as_overall_outcome() -> None:
    model = ReportModel(model="openai/test-model", report={
        "outcome": "satisfied", "summary": "A criterion was satisfied.",
    })
    with pytest.raises(ValidationError, match="passed.*failed.*partial.*inconclusive"):
        await run_report(model)


def test_malformed_json_is_never_silently_reclassified_as_a_pass() -> None:
    with pytest.raises(ValidationError, match="Invalid JSON"):
        _parse_persona_report('{"outcome":"passed","summary":"Result "AI" opened"}')
