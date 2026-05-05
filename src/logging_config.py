import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, cast, Union, Optional

DEFAULT_CONTEXT_FIELDS = {
    "thread_id": "-",
    "message_id": "-",
    "response_id": "-",
}


class ContextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        for field_name, default_value in DEFAULT_CONTEXT_FIELDS.items():
            if not hasattr(record, field_name):
                setattr(record, field_name, default_value)
        return super().format(record)


def build_formatter() -> logging.Formatter:
    formatter = ContextFormatter(
        fmt=(
            "%(asctime)s - [%(name)s] - %(levelname)s - "
            "[thread=%(thread_id)s msg=%(message_id)s resp=%(response_id)s] - %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    formatter.converter = time.gmtime
    return formatter


def configure_logging(
        level: int = logging.INFO,
        *,
        log_dir: Optional[Path] = None,
        console_level: int = logging.CRITICAL,
) -> Path:
    target_log_dir = log_dir or Path(__file__).resolve().parent.parent / "logs"
    target_log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    log_file = target_log_dir / f"{timestamp}.log"
    formatter = build_formatter()

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return log_file


def bind_logger(
        logger: Union[logging.Logger, logging.LoggerAdapter[Any]],
        **context: Optional[str],
) -> logging.LoggerAdapter[Any]:
    if isinstance(logger, logging.LoggerAdapter):
        base_logger = cast(logging.Logger, cast(object, logger.logger))
        combined_context: dict[str, Any] = dict(cast(Mapping[str, Any], logger.extra))
    else:
        base_logger = logger
        combined_context = {}

    combined_context.update({key: value for key, value in context.items() if value is not None})
    return logging.LoggerAdapter(base_logger, combined_context)
