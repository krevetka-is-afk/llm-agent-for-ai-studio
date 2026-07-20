import logging

from logging_config import build_formatter


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
