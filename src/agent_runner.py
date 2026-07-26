from dataclasses import dataclass
from typing import Literal, Protocol

from agent_runtime import ExecutableAgentConfig


@dataclass(frozen=True)
class AgentCitation:
    kind: Literal["file", "url"]
    title: str | None = None
    url: str | None = None
    file_id: str | None = None
    filename: str | None = None


@dataclass(frozen=True)
class AgentRunPreview:
    response_id: str
    output_text: str
    citations: tuple[AgentCitation, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class AgentRunner(Protocol):
    def run(
        self,
        config: ExecutableAgentConfig,
        user_input: str,
    ) -> AgentRunPreview: ...


class AgentRunnerError(RuntimeError):
    """Base class for safe generated-agent execution errors."""


class VectorStoreUnavailableError(AgentRunnerError):
    def __init__(self, vector_store_id: str, status: str) -> None:
        self.vector_store_id = vector_store_id
        self.status = status
        super().__init__(f"Vector Store is unavailable (status={status})")


class AgentProviderTimeoutError(AgentRunnerError):
    def __init__(self) -> None:
        super().__init__("Agent provider request timed out")


class AgentProviderError(AgentRunnerError):
    def __init__(
        self,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        super().__init__("Agent provider request failed")
