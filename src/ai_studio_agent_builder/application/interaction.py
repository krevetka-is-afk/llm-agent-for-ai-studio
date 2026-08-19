"""Provider-neutral contracts for the interactive Agent Builder use case."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from ai_studio_agent_builder.domain.routing import ConversationOptions
from ai_studio_agent_builder.domain.runtime import ExecutableAgentConfig

from .builder_state import ConversationState
from .dto import AIStudioCredentials
from .ports.agent_runner import AgentCitation


MAX_ATTACHMENTS_PER_REQUEST = 5
MAX_TOTAL_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_AGENT_TEST_INPUT_LENGTH = 10_000
MAX_GENERATED_FILES_PER_REQUEST = 10
MAX_GENERATED_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_GENERATED_BYTES = 25 * 1024 * 1024
UPLOAD_RETENTION_POLICY = (
    "Local user upload directories are removed when the user resets the conversation. "
    "Temporary provider input files have a maximum 48-hour lifetime; RAG vector "
    "stores expire after one day. Failed builds are cleaned up immediately on a "
    "best-effort basis."
)


class UploadValidationError(ValueError):
    """Raised when attachment metadata or content violates upload policy."""


class AgentTestInputError(ValueError):
    """Raised when an agent preview request has invalid user input."""


class AgentSpecificationImportError(ValueError):
    """Raised when an uploaded AgentSpecification cannot be imported."""


@dataclass(frozen=True)
class Attachment:
    filename: str
    display_name: str | None = None
    caption: str | None = None
    file_id: str | None = None


@dataclass(frozen=True)
class GeneratedFile:
    local_name: str
    display_name: str
    mime_type: str
    size_bytes: int
    inline_preview_allowed: bool


GeneratedFileWarningCode = Literal[
    "too_many",
    "too_large",
    "download_failed",
    "policy_blocked",
    "cleanup_failed",
]


@dataclass(frozen=True)
class GeneratedFileWarning:
    code: GeneratedFileWarningCode


@dataclass(frozen=True)
class InteractionRequest:
    user_id: str
    text: str | None
    credentials: AIStudioCredentials
    conversation_state: ConversationState
    user_files_dir: Path
    request_id: str = field(default_factory=lambda: uuid4().hex)
    attachment: Attachment | None = None
    attachments: tuple[Attachment, ...] = ()


@dataclass(frozen=True)
class InteractionResult:
    text: str
    parts: tuple[dict[str, Any], ...]
    selected_agent: ConversationOptions
    responded_by: ConversationOptions
    next_state: ConversationOptions


@dataclass(frozen=True)
class AgentTestRequest:
    user_id: str
    credentials: AIStudioCredentials
    specification_record: Mapping[str, Any]
    user_input: str
    request_id: str = field(default_factory=lambda: uuid4().hex)
    attachments: tuple[Attachment, ...] = ()


@dataclass(frozen=True)
class AgentTestResult:
    response_id: str
    output_text: str
    citations: tuple[AgentCitation, ...]
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    generated_files: tuple[GeneratedFile, ...] = ()
    generated_file_warnings: tuple[GeneratedFileWarning, ...] = ()


class AIInteraction(Protocol):
    """Operations required by interactive presentation adapters."""

    def user_files_dir(self, user_id: str) -> Path: ...

    def save_attachment(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        caption: str | None = None,
    ) -> Attachment: ...

    def read_generated_file(self, user_id: str, local_name: str) -> bytes: ...

    async def validate_connection(self, credentials: AIStudioCredentials) -> None: ...

    async def interact(self, request: InteractionRequest) -> InteractionResult: ...

    async def reset_conversation(self, user_id: str) -> None: ...

    def prepare_agent_runtime(
        self,
        specification_record: Mapping[str, Any],
    ) -> ExecutableAgentConfig: ...

    async def test_agent_specification(
        self,
        request: AgentTestRequest,
    ) -> AgentTestResult: ...


__all__ = [
    "AIInteraction",
    "AgentSpecificationImportError",
    "AgentTestInputError",
    "AgentTestRequest",
    "AgentTestResult",
    "Attachment",
    "GeneratedFile",
    "GeneratedFileWarning",
    "GeneratedFileWarningCode",
    "InteractionRequest",
    "InteractionResult",
    "MAX_AGENT_TEST_INPUT_LENGTH",
    "MAX_ATTACHMENTS_PER_REQUEST",
    "MAX_GENERATED_FILE_BYTES",
    "MAX_GENERATED_FILES_PER_REQUEST",
    "MAX_TOTAL_GENERATED_BYTES",
    "MAX_TOTAL_UPLOAD_BYTES",
    "UPLOAD_RETENTION_POLICY",
    "UploadValidationError",
]
