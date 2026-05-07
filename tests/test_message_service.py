from src.message_service import MessageService


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
