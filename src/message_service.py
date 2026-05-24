import logging
import io
from html import escape
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openai.types.responses import ResponseTextDeltaEvent

from config import Settings
from context import (
    get_user_client,
    RequestContext,
    ConversationState,
    ConversationOptions,
)
from custom_agents.rag_agent import build_rag_agent
from custom_agents.one_prompt_agent import build_one_prompt_agent
from custom_agents.coordinator_agent import build_coordinator_agent

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
    def __init__(self, settings: Settings):
        self._settings = settings
        self._rag_server = build_rag_agent(settings)
        self._one_prompt_server = build_one_prompt_agent(settings)
        self._coordinator_server = build_coordinator_agent(settings)

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
        conversation_state: ConversationState,
        base_dir: Path,
        combined_prompt: str,
    ) -> str:
        user_client = get_user_client(api_token, folder_id, self._settings)
        context = RequestContext(
            user_id=user_id,
            user_files_dir=base_dir,
            client=user_client,
            state=conversation_state,
        )

        if conversation_state.state == ConversationOptions.COORDINATOR:
            logging.info(f"Call coordinator llm with prompt {combined_prompt}")
            output = await self._get_streaming_response(
                self._coordinator_server, combined_prompt, context=context
            )
            logging.info(f"{output=} {conversation_state.state=}")

        if conversation_state.state == ConversationOptions.RAG:
            logging.info(f"Call coordinator llm with prompt {combined_prompt}")
            output = await self._get_streaming_response(
                self._rag_server, combined_prompt, context=context
            )
            logging.info(f"{output=} {conversation_state.state=}")
        elif conversation_state.state == ConversationOptions.ONE_PROMPT:
            logging.info(f"Call one_prompt llm with prompt {combined_prompt}")
            output = await self._get_streaming_response(
                self._one_prompt_server, combined_prompt, context=context
            )
            logging.info(f"{output=} {conversation_state=}")

        return output

    @staticmethod
    async def _get_streaming_response(
        model_server, input_user_message, context: RequestContext
    ):
        output = io.StringIO()
        async for event in model_server.respond(
            message=input_user_message, context=context
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
        "одну из её функций (загрузка, индексация, поиск, кино‑поиск)."
    )
