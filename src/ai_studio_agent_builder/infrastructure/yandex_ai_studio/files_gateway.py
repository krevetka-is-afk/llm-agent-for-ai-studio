from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from openai import APIError, APITimeoutError

from ...application.dto import AIStudioCredentials
from ...application.file_policy import enforce_upload_size, resolve_upload_path
from ...application.ports.agent_runner import (
    AgentProviderError,
    AgentProviderTimeoutError,
)
from ...application.ports.file_resource_gateway import FileResourceGateway


class _StreamingBinaryResponse(Protocol):
    def iter_bytes(self, chunk_size: int | None = None) -> Iterator[bytes]: ...


class _StreamingFilesResource(Protocol):
    def content(
        self,
        file_id: str,
    ) -> AbstractContextManager[_StreamingBinaryResponse]: ...


class _FilesResource(Protocol):
    def create(self, *, file: BinaryIO, purpose: str) -> Any: ...

    def delete(self, file_id: str) -> Any: ...

    @property
    def with_streaming_response(self) -> _StreamingFilesResource: ...


class _ContainersResource(Protocol):
    def delete(self, container_id: str) -> Any: ...


class _UploadClient(Protocol):
    @property
    def files(self) -> _FilesResource: ...

    @property
    def containers(self) -> _ContainersResource: ...


def upload_local_file(client: _UploadClient, base_dir: Path, filename: str) -> str:
    """Upload one policy-validated local file and return its provider file ID."""
    return _upload_local_file(
        client,
        base_dir,
        filename,
        purpose="assistants",
    )


def _upload_local_file(
    client: _UploadClient,
    base_dir: Path,
    filename: str,
    *,
    purpose: str,
) -> str:
    path = resolve_upload_path(base_dir, filename)
    enforce_upload_size(path, source_name=filename)
    try:
        with path.open("rb") as file:
            uploaded_file = client.files.create(file=file, purpose=purpose)
    except (APITimeoutError, TimeoutError) as exc:
        raise AgentProviderTimeoutError() from exc
    except APIError as exc:
        raise _provider_error(exc) from exc
    except Exception as exc:
        raise AgentProviderError() from exc
    file_id = getattr(uploaded_file, "id", None)
    if not isinstance(file_id, str) or not file_id:
        raise AgentProviderError()
    return file_id


class YandexFileResourceGateway(FileResourceGateway):
    def __init__(self, client: _UploadClient) -> None:
        self._client = client

    def upload_user_file(self, base_dir: Path, filename: str) -> str:
        return _upload_local_file(
            self._client,
            base_dir,
            filename,
            purpose="user_data",
        )

    def iter_file_bytes(
        self,
        file_id: str,
        *,
        chunk_size: int,
    ) -> Iterator[bytes]:
        try:
            with self._client.files.with_streaming_response.content(
                file_id
            ) as response:
                yield from response.iter_bytes(chunk_size=chunk_size)
        except (APITimeoutError, TimeoutError) as exc:
            raise AgentProviderTimeoutError() from exc
        except APIError as exc:
            raise _provider_error(exc) from exc
        except Exception as exc:
            raise AgentProviderError() from exc

    def delete_file(self, file_id: str) -> None:
        try:
            self._client.files.delete(file_id)
        except (APITimeoutError, TimeoutError) as exc:
            raise AgentProviderTimeoutError() from exc
        except APIError as exc:
            raise _provider_error(exc) from exc
        except Exception as exc:
            raise AgentProviderError() from exc

    def delete_container(self, container_id: str) -> None:
        try:
            self._client.containers.delete(container_id)
        except (APITimeoutError, TimeoutError) as exc:
            raise AgentProviderTimeoutError() from exc
        except APIError as exc:
            raise _provider_error(exc) from exc
        except Exception as exc:
            raise AgentProviderError() from exc


class YandexFileResourceGatewayFactory:
    def __init__(self, client_factory: Any) -> None:
        self._client_factory = client_factory

    def create(self, credentials: AIStudioCredentials) -> YandexFileResourceGateway:
        return YandexFileResourceGateway(self._client_factory(credentials))


def _provider_error(exc: APIError) -> AgentProviderError:
    status_code = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    return AgentProviderError(
        status_code=status_code if isinstance(status_code, int) else None,
        error_code=code if isinstance(code, str) else None,
    )


__all__ = [
    "YandexFileResourceGateway",
    "YandexFileResourceGatewayFactory",
    "upload_local_file",
]
