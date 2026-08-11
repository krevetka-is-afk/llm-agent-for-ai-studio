import asyncio

from ai_studio_agent_builder.presentation.telegram.handlers import (
    _delete_secret_messages,
)


class FakeBot:
    def __init__(self, fail_on: int | None = None) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.fail_on = fail_on

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        if message_id == self.fail_on:
            raise RuntimeError("Telegram rejected deletion")
        self.deleted.append((chat_id, message_id))
        return True


def test_secret_source_messages_are_deleted_after_connection_validation() -> None:
    bot = FakeBot()

    deleted = asyncio.run(_delete_secret_messages(bot, chat_id=7, message_ids=(10, 11)))

    assert deleted is True
    assert bot.deleted == [(7, 10), (7, 11)]


def test_failed_secret_message_deletion_is_reported_to_caller() -> None:
    bot = FakeBot(fail_on=11)

    deleted = asyncio.run(_delete_secret_messages(bot, chat_id=7, message_ids=(10, 11)))

    assert deleted is False
    assert bot.deleted == [(7, 10)]
