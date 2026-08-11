import logging

from ai_studio_agent_builder.infrastructure.observability.logging import (
    build_formatter,
    configure_logging,
)


def test_context_formatter_renders_request_id() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="done",
        args=(),
        exc_info=None,
    )
    record.user_id = "42"
    record.request_id = "request-42"

    rendered = build_formatter().format(record)

    assert "user=42" in rendered
    assert "req=request-42" in rendered


def test_default_file_logging_uses_runtime_working_directory(
    tmp_path, monkeypatch
) -> None:
    root_logger = logging.getLogger()
    previous_handlers = list(root_logger.handlers)
    previous_level = root_logger.level
    monkeypatch.chdir(tmp_path)

    try:
        log_file = configure_logging()

        assert log_file.parent == tmp_path / "logs"
        assert log_file.exists()
    finally:
        active_handlers = list(root_logger.handlers)
        root_logger.handlers[:] = previous_handlers
        root_logger.setLevel(previous_level)
        for handler in active_handlers:
            if handler not in previous_handlers:
                handler.close()
