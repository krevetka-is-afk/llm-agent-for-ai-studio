from dataclasses import dataclass
from typing import Any, AsyncIterator

from openai.types.responses import ResponseTextDeltaEvent

from src.context import RequestContext
from src.engine_skill import EngineCard
from src.message_service import MessageService
from src.primary_consultant import RouteDecision


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
