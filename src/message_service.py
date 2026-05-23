import logging
import io
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from openai.types.responses import ResponseTextDeltaEvent

from src.config import Settings
from src.context import RequestContext, get_user_client
from src.engine_skill import EngineCard, EngineSkill, EngineSkillRegistry
from src.primary_consultant import PrimaryConsultant
from src.rag.rag_skill import RagEngineSkill

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandHelp:
    command: str
    args_hint: Optional[str]
    description: str


COMMANDS = [
    CommandHelp(
        command="/help",
        args_hint=None,
        description="Показать доступные команды",
    ),
    CommandHelp(
        command="/skills",
        args_hint=None,
        description="Показать подключенные engine cards",
    ),
    CommandHelp(
        command="/reset",
        args_hint=None,
        description="сбросить текущую сессию",
    ),
    CommandHelp(
        command="/set_api_token",
        args_hint="<token>",
        description="сохранить API токен",
    ),
    CommandHelp(
        command="/set_folder_id",
        args_hint="<folder_id>",
        description="сохранить folder id",
    ),
]


class MessageService:
    def __init__(
        self,
        settings: Settings,
        skills: Optional[Iterable[EngineSkill]] = None,
        default_skill_id: str = "rag",
        primary_consultant: Optional[PrimaryConsultant] = None,
    ):
        self._settings = settings
        self._skill_registry = EngineSkillRegistry(skills or (RagEngineSkill(settings),))
        self._primary_consultant = primary_consultant or PrimaryConsultant(
            self._skill_registry,
            fallback_skill_id=default_skill_id,
        )

    @property
    def engine_cards(self) -> tuple[EngineCard, ...]:
        return self._skill_registry.cards

    @staticmethod
    def build_prompt(
        *,
        text: Optional[str],
        caption: Optional[str],
        file_name: Optional[str],
    ) -> str:
        if file_name and caption:
            return f"Uploaded file by user: {file_name} with request: {caption}\n"
        if file_name:
            return f"Uploaded file by user: {file_name}\n"
        return f"User request: {text or ''}\n"

    async def generate_response(
        self,
        *,
        user_id: str,
        api_token: str,
        folder_id: str,
        base_dir: Path,
        combined_prompt: str,
    ) -> str:
        user_client = get_user_client(api_token, folder_id, self._settings)
        context = RequestContext(
            user_id=user_id,
            user_files_dir=base_dir,
            client=user_client,
        )

        logging.info(f"Call llm with prompt {combined_prompt}")
        output = await self._get_streaming_response(combined_prompt, context=context)
        logging.info(f"{output=}")
        return output

    async def _get_streaming_response(
        self, input_user_message, context: RequestContext
    ):
        output = io.StringIO()
        route_decision = self._primary_consultant.route(input_user_message)
        selected_skill = self._skill_registry.require(route_decision.skill_id)
        logger.info(
            "Primary consultant routed request to %s: %s",
            route_decision.skill_id,
            route_decision.reason,
        )

        async for event in selected_skill.respond(
            input_user_message=input_user_message, context=context
        ):
            if event.type == "raw_response_event" and isinstance(
                event.data, ResponseTextDeltaEvent
            ):
                output.write(event.data.delta)
        return output.getvalue()

    @staticmethod
    def render_help_msg() -> str:
        lines = ["<b>Доступные команды</b>"]
        for cmd in COMMANDS:
            if cmd.args_hint:
                head = f"<code>{cmd.command} {escape(cmd.args_hint)}</code>"
            else:
                head = cmd.command

            lines.append(f"{head} — {cmd.description}")

        return "\n".join(lines)

    def render_engine_cards_msg(self) -> str:
        lines = ["<b>Доступные skills</b>"]
        for card in self.engine_cards:
            lines.append(
                f"<b>{escape(card.name)}</b> — <code>{escape(card.skill_id)}</code>"
            )
            lines.append(escape(card.description))
            if card.tags:
                rendered_tags = ", ".join(escape(tag) for tag in card.tags)
                lines.append(f"Tags: {rendered_tags}")
            if card.tools:
                rendered_tools = ", ".join(
                    f"<code>{escape(tool_name)}</code>" for tool_name in card.tools
                )
                lines.append(f"Tools: {rendered_tools}")

        return "\n".join(lines)

    @staticmethod
    def _find_command(command_name: str) -> Optional[CommandHelp]:
        for cmd in COMMANDS:
            if cmd.command == command_name:
                return cmd
        return None

    @classmethod
    def render_command_usage_msg(cls, command_name: str, intro: str) -> str:
        cmd = cls._find_command(command_name)
        if cmd is None or cmd.args_hint is None:
            return intro

        usage = f"{cmd.command} {cmd.args_hint}"
        return f"{intro}\nПопробуйте так: <code>{escape(usage)}</code>"

    welcome_message = (
        "Привет! Я — бот‑помощник с функциями LLM‑управления.\n"
        "Отправьте любой запрос, а я решу, какая из моих возможностей вам нужна.\n"
        "Перед началом работы отправь свой api-token и folder-id\n"
        "Текст переданный без команды будет обработан LLM‑моделью, которая может вызвать "
        "один из подключенных skills."
    )
