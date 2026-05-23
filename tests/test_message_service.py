import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, cast

from openai import OpenAI
from openai.types.responses import ResponseTextDeltaEvent

from src.context import RequestContext
from src.engine_skill import EngineCard, EngineSkillRegistry
from src.message_service import MessageService
from src.primary_consultant import PrimaryConsultant, RouteDecision
from src.rag.rag_skill import RAG_ENGINE_CARD


def test_render_command_usage_message_for_missing_argument_contains_usage() -> None:
    message = MessageService.render_command_usage_msg(
        "/set_api_token",
        "Команда вызвана без аргументов.",
    )

    assert "без аргументов" in message
    assert "<code>/set_api_token &lt;token&gt;</code>" in message


def test_render_command_usage_message_contains_intro_and_usage() -> None:
    message = MessageService.render_command_usage_msg(
        "/set_folder_id",
        "Сначала сохраните folder id.",
    )

    assert "Сначала сохраните folder id." in message
    assert "<code>/set_folder_id &lt;folder_id&gt;</code>" in message


def test_render_help_message_contains_skills_command() -> None:
    message = MessageService.render_help_msg()

    assert "/skills" in message
    assert "engine cards" in message


def test_rag_skill_has_engine_card() -> None:
    assert RAG_ENGINE_CARD.skill_id == "rag"
    assert RAG_ENGINE_CARD.input_modes == ("text/plain",)
    assert RAG_ENGINE_CARD.output_modes == ("text/plain",)
    assert "vector-store" in RAG_ENGINE_CARD.tags
    assert "search_in_vector_index" in RAG_ENGINE_CARD.tools


def test_engine_card_can_be_rendered_as_a2a_skill() -> None:
    a2a_skill = RAG_ENGINE_CARD.to_a2a_skill()

    assert a2a_skill["id"] == "rag"
    assert a2a_skill["name"] == "RAG search skill"
    assert a2a_skill["tags"] == ["rag", "files", "vector-store", "search"]
    assert a2a_skill["inputModes"] == ["text/plain"]
    assert a2a_skill["outputModes"] == ["text/plain"]


def test_render_engine_cards_message_contains_rag_skill() -> None:
    class FakeRegistry:
        cards = (RAG_ENGINE_CARD,)

    message = MessageService.__new__(MessageService)
    message._skill_registry = FakeRegistry()

    rendered = message.render_engine_cards_msg()

    assert "<code>rag</code>" in rendered
    assert "vector-store" in rendered
    assert "search_in_vector_index" in rendered


def test_primary_consultant_routes_to_matching_skill_card() -> None:
    rag_skill = FakeSkill(RAG_ENGINE_CARD, "rag")
    one_prompt_skill = FakeSkill(
        EngineCard(
            skill_id="one_prompt",
            name="One prompt skill",
            description="Generates a direct model response from a fixed prompt.",
            tags=("prompt", "direct", "generation"),
            examples=("Answer directly from this prompt.",),
        ),
        "one prompt",
    )
    registry = EngineSkillRegistry((rag_skill, one_prompt_skill))
    consultant = PrimaryConsultant(registry, fallback_skill_id="rag")

    decision = consultant.route("Please answer directly from this prompt")

    assert decision.skill_id == "one_prompt"


def test_message_service_uses_primary_consultant_route() -> None:
    rag_skill = FakeSkill(RAG_ENGINE_CARD, "wrong")
    target_skill = FakeSkill(
        EngineCard(
            skill_id="target",
            name="Target skill",
            description="Used by test route.",
            tags=("target",),
        ),
        "selected",
    )
    service = MessageService.__new__(MessageService)
    service._skill_registry = EngineSkillRegistry((rag_skill, target_skill))
    service._primary_consultant = FakePrimaryConsultant("target")
    context = RequestContext(
        user_id="user-id",
        user_files_dir=Path("/tmp"),
        client=cast(OpenAI, object()),
    )

    output = asyncio.run(service._get_streaming_response("route me", context))

    assert output == "selected"


@dataclass(frozen=True)
class FakePrimaryConsultant:
    skill_id: str

    def route(self, input_user_message: str) -> RouteDecision:
        return RouteDecision(skill_id=self.skill_id, reason=input_user_message)


@dataclass(frozen=True)
class FakeSkill:
    card: EngineCard
    response: str

    async def respond(
        self,
        input_user_message: str,
        context: RequestContext,
    ) -> AsyncIterator[Any]:
        yield FakeRawResponseEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta=self.response,
                item_id="item-id",
                logprobs=[],
                output_index=0,
                sequence_number=0,
                type="response.output_text.delta",
            )
        )


@dataclass(frozen=True)
class FakeRawResponseEvent:
    data: ResponseTextDeltaEvent
    type: str = "raw_response_event"
