from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, Protocol

from context import RequestContext


@dataclass(frozen=True)
class EngineCard:
    skill_id: str
    description: str
    name: str
    tags: tuple[str, ...]
    examples: tuple[str, ...] = ()
    input_modes: tuple[str, ...] = ("text/plain",)
    output_modes: tuple[str, ...] = ("text/plain",)
    tools: tuple[str, ...] = ()

    def to_a2a_skill(self) -> dict[str, object]:
        return {
            "id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "examples": list(self.examples),
            "inputModes": list(self.input_modes),
            "outputModes": list(self.output_modes),
        }


class EngineSkill(Protocol):
    card: EngineCard

    def respond(
        self,
        input_user_message: str,
        context: RequestContext,
    ) -> AsyncIterator[Any]:
        """Return streamed events for a user request handled by this skill."""
        ...


class EngineSkillRegistry:
    def __init__(self, skills: Iterable[EngineSkill]):
        skill_list = tuple(skills)
        self._skills_by_id = {skill.card.skill_id: skill for skill in skill_list}
        if len(self._skills_by_id) != len(skill_list):
            raise ValueError("Engine skill ids must be unique")

    @property
    def cards(self) -> tuple[EngineCard, ...]:
        return tuple(skill.card for skill in self._skills_by_id.values())

    def require(self, skill_id: str) -> EngineSkill:
        try:
            return self._skills_by_id[skill_id]
        except KeyError as e:
            raise ValueError(f"Unknown engine skill: {skill_id}") from e
