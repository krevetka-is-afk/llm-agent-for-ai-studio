from html import escape
from dataclasses import dataclass
from typing import Optional


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
        description="сохранить API-ключ",
    ),
    CommandHelp(
        command="/set_folder_id",
        args_hint="<folder_id>",
        description="сохранить folder ID",
    ),
]


class MessageService:
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
        "Подключите Yandex Cloud командами /set_api_token и /set_folder_id.\n"
        "Текст переданный без команды будет обработан LLM‑моделью, которая может вызвать "
        "одну из её функций (загрузка, индексация, поиск)."
    )
