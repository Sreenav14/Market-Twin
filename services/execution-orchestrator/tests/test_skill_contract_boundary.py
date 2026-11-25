"""Source guidance must not masquerade as executable automation."""

from markettwin_shared.knowledge import SkillDefinition

from markettwin_execution_orchestrator.workflow.skill_filter import skill_selectability


def test_documented_procedure_round_trips_without_becoming_replayable():
    definition = SkillDefinition(
        intent="Invite a teammate",
        procedure=("Open Members", "Enter the teammate email", "Send invitation"),
        inputs=("Teammate email",),
        expected_outcomes=("Invitation appears as pending",),
    )
    restored = SkillDefinition.model_validate_json(definition.model_dump_json())
    assert restored.procedure == definition.procedure
    assert skill_selectability(
        restored.model_dump(mode="json"), mode="explore", approved_keys=set()
    ) == "mode_filter"


def test_empty_steps_cannot_be_selected_as_executable_skill():
    assert skill_selectability(
        {"steps": []}, mode="explore", approved_keys=set()
    ) == "mode_filter"


def test_historical_capability_has_no_invented_procedure():
    definition = SkillDefinition(intent="Search", expected_outcomes=("Results appear",))
    assert definition.procedure == ()
