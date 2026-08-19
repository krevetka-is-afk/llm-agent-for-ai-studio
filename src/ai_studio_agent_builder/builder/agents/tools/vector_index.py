import json
import logging
import time
from collections.abc import Callable
from typing import Any

from agents import RunContextWrapper, function_tool

from ai_studio_agent_builder.application.errors import VectorIndexUnavailableError
from ai_studio_agent_builder.builder.context import (
    BuilderResourceClient,
    RequestContext,
)
from openai.types import (
    vector_store_create_params,
    StaticFileChunkingStrategyObjectParam,
    StaticFileChunkingStrategyParam,
)

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


class VectorIndexPollingError(VectorIndexUnavailableError):
    """Base class for bounded vector store polling failures."""


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
    return logging.LoggerAdapter(
        logger,
        {"user_id": ctx.context.user_id, "request_id": ctx.context.request_id},
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

    client: BuilderResourceClient = ctx.context.client
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

    try:
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
    except BaseException:
        try:
            client.vector_stores.delete(vector_store_id)
        except Exception as exc:
            tool_logger.warning(
                "Vector Store cleanup failed after index build error category=%s",
                type(exc).__name__,
            )
        raise

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


def _tool_result(
    *,
    status: str,
    index_id: str | None = None,
    index_name: str | None = None,
    file_ids: tuple[str, ...] = (),
    message: str | None = None,
) -> str:
    result: dict[str, Any] = {"status": status}
    if index_id is not None:
        result["index_id"] = index_id
    if index_name is not None:
        result["index_name"] = index_name
    if file_ids:
        result["file_ids"] = list(file_ids)
    if message is not None:
        result["message"] = message
    return json.dumps(result, ensure_ascii=False)


def _existing_vector_index(ctx: Any) -> tuple[str, str, tuple[str, ...]] | None:
    state = getattr(ctx.context, "state", None)
    specification = getattr(state, "agent_specification", None)
    if specification is None:
        return None
    index_id = specification.parameters.get("index_id")
    index_name = specification.parameters.get("index_name")
    if not isinstance(index_id, str) or not index_id:
        return None
    if not isinstance(index_name, str) or not index_name:
        return None
    file_ids = tuple(
        source.source_id
        for source in specification.knowledge_sources
        if source.kind == "uploaded_file"
    )
    return index_id, index_name, file_ids


def _create_search_index_for_context(ctx: Any, vector_store_name: str) -> str:
    state = getattr(ctx.context, "state", None)
    pending_file_ids = tuple(getattr(state, "pending_file_ids", ()))
    if not pending_file_ids:
        existing = _existing_vector_index(ctx)
        if existing is not None:
            index_id, index_name, file_ids = existing
            _tool_logger(ctx).info(
                "Vector Store already attached; reusing %s", index_id
            )
            return _tool_result(
                status="exists",
                index_id=index_id,
                index_name=index_name,
                file_ids=file_ids,
            )
        return _tool_result(
            status="needs_files",
            message=(
                "No uploaded files are available for this RAG workflow. "
                "Ask the user to attach the files."
            ),
        )

    index_id = _create_search_index_impl(
        ctx,
        list(pending_file_ids),
        vector_store_name,
    )
    return _tool_result(
        status="created",
        index_id=index_id,
        index_name=vector_store_name,
        file_ids=pending_file_ids,
    )


@function_tool
def create_search_index(
    ctx: RunContextWrapper[RequestContext], vector_store_name: str
) -> str:
    """
    Build a vector store from the files managed by the current RAG workflow.

    Args:
        vector_store_name: Human-readable name for the vector store.

    Returns:
        A structured status with the created or existing vector store.
        :param vector_store_name:
        :param ctx:
    """
    return _create_search_index_for_context(ctx, vector_store_name)
