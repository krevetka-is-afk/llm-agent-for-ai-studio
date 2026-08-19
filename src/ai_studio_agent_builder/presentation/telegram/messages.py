"""Telegram-specific help and command messages."""

from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class CommandHelp:
    command: str
    args_hint: str | None
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
    CommandHelp(
        command="/clear_credentials",
        args_hint=None,
        description="удалить API-ключ, folder ID и историю сессии",
    ),
]


class MessageService:
    @staticmethod
    def render_help_msg() -> str:
        lines = ["<b>Доступные команды</b>"]
        for command in COMMANDS:
            if command.args_hint:
                head = f"<code>{command.command} {escape(command.args_hint)}</code>"
            else:
                head = command.command
            lines.append(f"{head} — {command.description}")
        return "\n".join(lines)

    @staticmethod
    def _find_command(command_name: str) -> CommandHelp | None:
        for command in COMMANDS:
            if command.command == command_name:
                return command
        return None

    @classmethod
    def render_command_usage_msg(cls, command_name: str, intro: str) -> str:
        command = cls._find_command(command_name)
        if command is None or command.args_hint is None:
            return intro
        usage = f"{command.command} {command.args_hint}"
        return f"{intro}\nПопробуйте так: <code>{escape(usage)}</code>"

    welcome_message = (
        "Привет! Я — бот‑помощник с функциями LLM‑управления.\n"
        "Отправьте любой запрос, а я решу, какая из моих возможностей вам нужна.\n"
        "Подключите Yandex Cloud командами /set_api_token и /set_folder_id.\n"
        "Текст переданный без команды будет обработан LLM‑моделью, которая может "
        "вызвать одну из её функций (загрузка, индексация, поиск)."
    )


__all__ = ["COMMANDS", "CommandHelp", "MessageService"]
