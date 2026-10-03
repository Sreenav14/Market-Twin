"""Compatibility facade for callers that currently request only generated Skills."""

from markettwin_shared.knowledge import GeneratedSkillDraft, KnowledgeBuildResult

from markettwin_knowledge_worker.extraction import ExtractionResult
from markettwin_knowledge_worker.knowledge_builder import KnowledgeBuilder

# Existing callers and tests import this name. The schema now carries the complete knowledge result.
GeneratedSkills = KnowledgeBuildResult


class SkillGenerator:
    """Return Skills from the single Knowledge Builder semantic boundary."""

    def __init__(self, *, knowledge_builder: KnowledgeBuilder | None = None) -> None:
        self._knowledge_builder = knowledge_builder or KnowledgeBuilder()

    async def generate(self, extraction: ExtractionResult) -> tuple[GeneratedSkillDraft, ...]:
        """Build all knowledge, then return the durable Skill subset for current persistence."""
        return (await self._knowledge_builder.build(extraction)).skills
