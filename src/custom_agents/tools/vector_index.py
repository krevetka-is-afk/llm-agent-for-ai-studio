import logging
import time
from collections.abc import Callable
from typing import Any

from agents import RunContextWrapper, function_tool

from context import RequestContext
from openai import OpenAI
from openai.types import (
    vector_store_create_params,
    StaticFileChunkingStrategyObjectParam,
    StaticFileChunkingStrategyParam,
)

from logging_config import bind_logger

logger = logging.getLogger(__name__)

DEFAULT_VECTOR_STORE_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_VECTOR_STORE_POLL_TIMEOUT_SECONDS = 300.0
DEFAULT_VECTOR_STORE_MAX_ATTEMPTS = 100

_COMPLETED_STATUS = "completed"
_FAILED_STATUSES = frozenset({"failed", "cancelled", "expired"})
_WAITING_STATUSES = frozenset({"in_progress"})

DEFAULT_CHUNKING_STRATEGY = StaticFileChunkingStrategyObjectParam(
    type="static",
    static=StaticFileChunkingStrategyParam(
        max_chunk_size_tokens=1408, chunk_overlap_tokens=148
    ),
)


class VectorIndexPollingError(RuntimeError):
    """Base class for bounded vector store polling failures."""


class VectorIndexAuthorizationError(PermissionError):
    """Raised when the model references files outside the current request."""


class VectorIndexTerminalStatusError(VectorIndexPollingError):
    def __init__(self, vector_store_id: str, status: str) -> None:
        self.vector_store_id = vector_store_id
        self.status = status
        super().__init__(
            f"Vector Store {vector_store_id} finished with terminal status {status!r}"
        )


class VectorIndexUnknownStatusError(VectorIndexPollingError):
    def __init__(self, vector_store_id: str, status: Any, attempt: int) -> None:
        self.vector_store_id = vector_store_id
        self.status = status
        self.attempt = attempt
        super().__init__(
            "Vector Store "
            f"{vector_store_id} returned unsupported status {status!r} "
            f"on attempt {attempt}"
        )


class VectorIndexPollingTimeoutError(VectorIndexPollingError):
    def __init__(
        self,
        vector_store_id: str,
        last_status: Any,
        attempts: int,
        elapsed_seconds: float,
    ) -> None:
        self.vector_store_id = vector_store_id
        self.last_status = last_status
        self.attempts = attempts
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            "Vector Store "
            f"{vector_store_id} did not complete after {attempts} attempts "
            f"over {elapsed_seconds:.1f}s; last status={last_status!r}"
        )


def _tool_logger(ctx: RunContextWrapper[RequestContext]) -> logging.LoggerAdapter:
    return bind_logger(
        logger,
        user_id=ctx.context.user_id,
        request_id=ctx.context.request_id,
    )


def _wait_for_vector_store_completed(
    *,
    client: Any,
    vector_store_id: str,
    tool_logger: logging.Logger | logging.LoggerAdapter[Any],
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    poll_interval_seconds: float = DEFAULT_VECTOR_STORE_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_VECTOR_STORE_POLL_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_VECTOR_STORE_MAX_ATTEMPTS,
) -> None:
    started_at = monotonic()
    last_status: Any = None

    for attempt in range(1, max_attempts + 1):
        vector_store = client.vector_stores.retrieve(vector_store_id)
        last_status = getattr(vector_store, "status", None)

        if last_status == _COMPLETED_STATUS:
            return
        if last_status in _FAILED_STATUSES:
            raise VectorIndexTerminalStatusError(vector_store_id, last_status)
        if last_status not in _WAITING_STATUSES:
            raise VectorIndexUnknownStatusError(vector_store_id, last_status, attempt)

        elapsed_seconds = monotonic() - started_at
        if elapsed_seconds >= timeout_seconds:
            raise VectorIndexPollingTimeoutError(
                vector_store_id, last_status, attempt, elapsed_seconds
            )

        tool_logger.debug(
            "Vector Store %s status=%s; waiting", vector_store_id, last_status
        )
        if attempt < max_attempts:
            sleep(poll_interval_seconds)

    raise VectorIndexPollingTimeoutError(
        vector_store_id, last_status, max_attempts, monotonic() - started_at
    )


def _create_search_index_impl(
    ctx: Any,
    file_ids: list[str],
    vector_store_name: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
    poll_interval_seconds: float = DEFAULT_VECTOR_STORE_POLL_INTERVAL_SECONDS,
    timeout_seconds: float = DEFAULT_VECTOR_STORE_POLL_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_VECTOR_STORE_MAX_ATTEMPTS,
) -> str:
    tool_logger = _tool_logger(ctx)
    tool_logger.info("Создаем поисковый индекс с %s файлами", len(file_ids))

    client: OpenAI = ctx.context.client
    vector_store = client.vector_stores.create(
        name=vector_store_name,
        metadata={"key": "value"},
        expires_after=vector_store_create_params.ExpiresAfter(
            anchor="last_active_at", days=1
        ),
        chunking_strategy=DEFAULT_CHUNKING_STRATEGY,
        file_ids=file_ids,
    )
    vector_store_id = vector_store.id
    tool_logger.info("Vector Store создан: %s", vector_store_id)

    _wait_for_vector_store_completed(
        client=client,
        vector_store_id=vector_store_id,
        tool_logger=tool_logger,
        sleep=sleep,
        monotonic=monotonic,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
    )

    tool_logger.info("Vector Store %s готов к работе", vector_store_id)
    request_state = getattr(ctx.context, "state", None)
    if request_state is not None:
        request_state.attach_vector_index(
            index_id=vector_store_id,
            index_name=vector_store_name,
            file_ids=tuple(file_ids),
            source_titles=getattr(ctx.context, "filenames_by_file_id", None),
        )
    return vector_store_id


def _validate_authorized_file_ids(
    file_ids: list[str], allowed_file_ids: frozenset[str]
) -> None:
    if not file_ids:
        raise VectorIndexAuthorizationError(
            "A vector index requires files from the current request"
        )
    if len(file_ids) != len(set(file_ids)):
        raise VectorIndexAuthorizationError("Duplicate file IDs are not allowed")
    unauthorized = set(file_ids) - allowed_file_ids
    if unauthorized:
        raise VectorIndexAuthorizationError(
            "Vector index file IDs must come from the current request"
        )


@function_tool
def create_search_index(
    ctx: RunContextWrapper[RequestContext], file_ids: list[str], vector_store_name: str
) -> str:
    """
    Build a vector store from the provided files.

    Args:
        vector_store_name: Human-readable name for the vector store.
        file_ids: List of file ids to include in the vector store.

    Returns:
        The ID of the created vector store.
        :param vector_store_name:
        :param file_ids:
        :param ctx:
    """
    _validate_authorized_file_ids(file_ids, ctx.context.allowed_file_ids)
    return _create_search_index_impl(ctx, file_ids, vector_store_name)
