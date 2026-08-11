from collections.abc import Mapping, Sequence
from typing import Any

from openai import APIError, APITimeoutError, NotFoundError

from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentCitation,
    AgentProviderError,
    AgentProviderTimeoutError,
    AgentRunPreview,
    VectorStoreUnavailableError,
)
from ai_studio_agent_builder.domain.runtime import ExecutableAgentConfig


READY_VECTOR_STORE_STATUS = "completed"
UNAVAILABLE_VECTOR_STORE_STATUSES = frozenset(
    {"in_progress", "expired", "failed", "cancelled"}
)


class YandexResponsesAgentRunner:
    def __init__(self, client: Any, *, folder_id: str) -> None:
        self._client = client
        self._folder_id = folder_id

    def run(
        self,
        config: ExecutableAgentConfig,
        user_input: str,
    ) -> AgentRunPreview:
        self._preflight_file_search(config.tools)
        request: dict[str, Any] = {
            "model": f"gpt://{self._folder_id}/{config.model_name}",
            "instructions": config.instructions,
            "input": user_input,
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
        }
        if config.tools:
            request["tools"] = list(config.tools)
        try:
            response = self._client.responses.create(**request)
        except (APITimeoutError, TimeoutError) as exc:
            raise AgentProviderTimeoutError() from exc
        except APIError as exc:
            raise _provider_error(exc) from exc
        except Exception as exc:
            raise AgentProviderError() from exc
        return _normalize_response(response)

    def _preflight_file_search(self, tools: tuple[Mapping[str, Any], ...]) -> None:
        for tool in tools:
            if tool.get("type") != "file_search":
                continue
            vector_store_ids = tool.get("vector_store_ids")
            if not isinstance(vector_store_ids, Sequence) or isinstance(
                vector_store_ids, str | bytes | bytearray
            ):
                raise VectorStoreUnavailableError("unknown", "invalid_config")
            for vector_store_id in vector_store_ids:
                if not isinstance(vector_store_id, str) or not vector_store_id:
                    raise VectorStoreUnavailableError("unknown", "invalid_config")
                self._retrieve_vector_store(vector_store_id)

    def _retrieve_vector_store(self, vector_store_id: str) -> None:
        try:
            vector_store = self._client.vector_stores.retrieve(vector_store_id)
        except NotFoundError as exc:
            raise VectorStoreUnavailableError(vector_store_id, "not_found") from exc
        except (APITimeoutError, TimeoutError) as exc:
            raise AgentProviderTimeoutError() from exc
        except APIError as exc:
            raise _provider_error(exc) from exc
        except Exception as exc:
            raise AgentProviderError() from exc

        status = _value(vector_store, "status")
        if status == READY_VECTOR_STORE_STATUS:
            return
        if isinstance(status, str) and status in UNAVAILABLE_VECTOR_STORE_STATUSES:
            raise VectorStoreUnavailableError(vector_store_id, status)
        raise VectorStoreUnavailableError(vector_store_id, "unknown")


def _normalize_response(response: Any) -> AgentRunPreview:
    usage = _value(response, "usage")
    response_id = _value(response, "id")
    output_text = _value(response, "output_text")
    return AgentRunPreview(
        response_id=response_id if isinstance(response_id, str) else "",
        output_text=output_text if isinstance(output_text, str) else "",
        citations=_extract_citations(response),
        input_tokens=_optional_int(_value(usage, "input_tokens")),
        output_tokens=_optional_int(_value(usage, "output_tokens")),
        total_tokens=_optional_int(_value(usage, "total_tokens")),
    )


def _extract_citations(response: Any) -> tuple[AgentCitation, ...]:
    citations: list[AgentCitation] = []
    seen: set[tuple[Any, ...]] = set()
    output = _value(response, "output")
    if not isinstance(output, Sequence) or isinstance(output, str | bytes | bytearray):
        return ()
    for item in output:
        content = _value(item, "content")
        if not isinstance(content, Sequence) or isinstance(
            content, str | bytes | bytearray
        ):
            continue
        for content_item in content:
            annotations = _value(content_item, "annotations")
            if not isinstance(annotations, Sequence) or isinstance(
                annotations, str | bytes | bytearray
            ):
                continue
            for annotation in annotations:
                citation = _citation_from_annotation(annotation)
                if citation is None:
                    continue
                fingerprint = (
                    citation.kind,
                    citation.title,
                    citation.url,
                    citation.file_id,
                    citation.filename,
                )
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    citations.append(citation)
    return tuple(citations)


def _citation_from_annotation(annotation: Any) -> AgentCitation | None:
    annotation_type = _value(annotation, "type")
    if annotation_type == "url_citation":
        return AgentCitation(
            kind="url",
            title=_optional_string(_value(annotation, "title")),
            url=_optional_string(_value(annotation, "url")),
        )
    if annotation_type in {"file_citation", "container_file_citation", "file_path"}:
        filename = _optional_string(_value(annotation, "filename"))
        return AgentCitation(
            kind="file",
            title=filename,
            file_id=_optional_string(_value(annotation, "file_id")),
            filename=filename,
        )
    return None


def _provider_error(exc: APIError) -> AgentProviderError:
    status_code = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    return AgentProviderError(
        status_code=status_code if isinstance(status_code, int) else None,
        error_code=code if isinstance(code, str) else None,
    )


def _value(source: Any, name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name, None)


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
