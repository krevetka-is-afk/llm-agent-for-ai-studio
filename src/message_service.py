import logging
from html import escape
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from chatkit.types import ThreadMetadata

from src.config import Settings
from src.context import AppContext, ConversationState, RequestContext
from src.rag_agent_server import RagServer
from src.utils import get_streaming_response, get_user_client


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
    )
]


class MessageService:
    def __init__(self, settings: Settings):
        self._settings = settings

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
        client = get_user_client(api_token, folder_id, self._settings)
        rag_server = RagServer(self._settings, client)
        conversation_state = ConversationState(base_dir)
        thread = ThreadMetadata(
            id=user_id,
            created_at=datetime.now(timezone.utc),
            metadata={},
        )
        request_context: RequestContext = {
            "conv_context": conversation_state,
            "client": client,
        }
        context = AppContext(
            user_id=user_id,
            thread=thread,
            request_context=request_context,
        )

        logging.info(f"Call llm with prompt {combined_prompt}")
        output = await get_streaming_response(rag_server, thread, combined_prompt, context=context)
        logging.info(f"{output=}")
        return output

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
        return (
            f"{intro}\n"
            f"Попробуйте так: <code>{escape(usage)}</code>"
        )

    welcome_message = (
        "Привет! Я — бот‑помощник с функциями LLM‑управления.\n"
        "Отправьте любой запрос, а я решу, какая из моих возможностей вам нужна.\n"
        "Перед началом работы отправь свой api-token и folder-id\n"
        "Текст переданный без команды будет обработан LLM‑моделью, которая может вызвать "
        "одну из её функций (загрузка, индексация, поиск, кино‑поиск)."
    )
