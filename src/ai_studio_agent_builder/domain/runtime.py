import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Protocol

from .specification import (
    CODE_INTERPRETER_MEMORY_LIMIT,
    CODE_INTERPRETER_NETWORK_POLICY,
    SCHEMA_VERSION as SPECIFICATION_SCHEMA_VERSION,
    AgentSpecification,
    AgentSpecificationStatus,
)
from .catalog import TemplateId


RUNTIME_SCHEMA_VERSION = "1.0"
REDACTED_VALUE = "[REDACTED]"


class AgentRuntimeSettings(Protocol):
    model_name: str
    temperature: float
    max_output_tokens: int


class AgentRuntimeCompilationError(ValueError):
    """Base class for deterministic specification compilation failures."""


class SpecificationNotReadyError(AgentRuntimeCompilationError):
    pass


class UnsupportedSpecificationVersionError(AgentRuntimeCompilationError):
    pass


class UnsupportedAgentToolError(AgentRuntimeCompilationError):
    pass


class MissingRuntimeParameterError(AgentRuntimeCompilationError):
    pass


class InvalidRuntimeFileBindingError(AgentRuntimeCompilationError):
    pass


class MissingCodeInterpreterToolError(InvalidRuntimeFileBindingError):
    pass


@dataclass(frozen=True)
class ExecutableAgentConfig:
    schema_version: str
    model_name: str
    instructions: str
    tools: tuple[Mapping[str, Any], ...]
    temperature: float
    max_output_tokens: int

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "model_name": self.model_name,
            "instructions": self.instructions,
            "tools": [_json_copy(tool) for tool in self.tools],
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_record(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )


def compile_agent_specification(
    specification: AgentSpecification,
    *,
    runtime: AgentRuntimeSettings,
) -> ExecutableAgentConfig:
    if specification.schema_version != SPECIFICATION_SCHEMA_VERSION:
        raise UnsupportedSpecificationVersionError(
            "Unsupported AgentSpecification schema version"
        )
    if _contains_redacted_value(specification.to_record()):
        raise MissingRuntimeParameterError(
            "Specification contains redacted runtime values"
        )

    native_tools = tuple(_compile_tool(tool) for tool in specification.tools)
    if specification.template is TemplateId.RAG:
        index_id = specification.parameters.get("index_id")
        if not isinstance(index_id, str) or not index_id.strip():
            raise MissingRuntimeParameterError("RAG specification requires index_id")

    validation = specification.validate()
    if (
        specification.status is not AgentSpecificationStatus.READY
        or not validation.is_ready
    ):
        raise SpecificationNotReadyError(
            "Only a ready AgentSpecification can be executed"
        )

    return ExecutableAgentConfig(
        schema_version=RUNTIME_SCHEMA_VERSION,
        model_name=runtime.model_name,
        instructions=_compile_instructions(specification),
        tools=native_tools,
        temperature=runtime.temperature,
        max_output_tokens=runtime.max_output_tokens,
    )


def bind_code_interpreter_files(
    config: ExecutableAgentConfig,
    file_ids: Sequence[str],
) -> ExecutableAgentConfig:
    """Return a request-scoped config containing only trusted provider file IDs."""
    code_tool_indexes = tuple(
        index
        for index, tool in enumerate(config.tools)
        if tool.get("type") == "code_interpreter"
    )
    if not code_tool_indexes:
        raise MissingCodeInterpreterToolError(
            "Code Interpreter attachments require a code_interpreter tool"
        )
    if len(code_tool_indexes) != 1:
        raise InvalidRuntimeFileBindingError(
            "Runtime must contain exactly one code_interpreter tool"
        )
    if isinstance(file_ids, str | bytes | bytearray):
        raise InvalidRuntimeFileBindingError("Provider file IDs must be a sequence")

    trusted_file_ids: list[str] = []
    for file_id in file_ids:
        if not isinstance(file_id, str) or not file_id.strip():
            raise InvalidRuntimeFileBindingError("Provider file ID is invalid")
        if file_id in trusted_file_ids:
            raise InvalidRuntimeFileBindingError("Provider file IDs must be unique")
        trusted_file_ids.append(file_id)

    base_code_tool = config.tools[code_tool_indexes[0]]
    base_container = base_code_tool.get("container")
    if not isinstance(base_container, Mapping) or base_container.get("type") != "auto":
        raise InvalidRuntimeFileBindingError(
            "Code Interpreter runtime requires an automatic container"
        )
    if "file_ids" in base_container:
        raise InvalidRuntimeFileBindingError(
            "Base runtime must not contain provider file IDs"
        )
    if not trusted_file_ids:
        return config

    tools = [_json_copy(tool) for tool in config.tools]
    tool_index = code_tool_indexes[0]
    code_tool = tools[tool_index]
    code_tool["container"] = {
        **dict(base_container),
        "file_ids": list(trusted_file_ids),
    }
    return replace(config, tools=tuple(tools))


def _compile_tool(tool: Any) -> Mapping[str, Any]:
    if tool.tool_id == "web_search":
        search_context_size = tool.parameters.get("search_context_size")
        if not isinstance(search_context_size, str) or not search_context_size:
            raise MissingRuntimeParameterError(
                "web_search requires search_context_size"
            )
        return {
            "type": "web_search",
            "search_context_size": search_context_size,
        }
    if tool.tool_id == "knowledge_search":
        index_id = tool.parameters.get("index_id")
        if not isinstance(index_id, str) or not index_id.strip():
            raise MissingRuntimeParameterError("knowledge_search requires index_id")
        return {
            "type": "file_search",
            "vector_store_ids": [index_id],
        }
    if tool.tool_id == "code_interpreter":
        memory_limit = tool.parameters.get("memory_limit")
        network_policy = tool.parameters.get("network_policy")
        if memory_limit != CODE_INTERPRETER_MEMORY_LIMIT:
            raise MissingRuntimeParameterError(
                "code_interpreter requires the supported memory limit"
            )
        if network_policy != CODE_INTERPRETER_NETWORK_POLICY:
            raise MissingRuntimeParameterError(
                "code_interpreter requires the supported network policy"
            )
        return {
            "type": "code_interpreter",
            "container": {
                "type": "auto",
                "memory_limit": memory_limit,
                "network_policy": {"type": network_policy},
            },
        }
    raise UnsupportedAgentToolError(
        f"Unsupported executable agent tool: {tool.tool_id!r}"
    )


def _compile_instructions(specification: AgentSpecification) -> str:
    sections = [
        _compile_identity_and_capabilities(specification),
        specification.instructions.strip(),
    ]
    if specification.constraints:
        constraints = "\n".join(
            f"- {constraint.strip()}" for constraint in specification.constraints
        )
        sections.append(f"Constraints:\n{constraints}")
    sections.append(f"Expected result:\n{specification.expected_result.strip()}")
    return "\n\n".join(sections)


def _compile_identity_and_capabilities(
    specification: AgentSpecification,
) -> str:
    lines = [
        "Agent identity and capabilities:",
        (
            "- You are an AI agent configured for this purpose: "
            f"{specification.purpose.strip()}"
        ),
        (
            "- Treat this purpose, these system instructions, and the capabilities "
            "listed here as authoritative context about your role."
        ),
        (
            "- When the user asks who you are, what you can do, or how you work, "
            "answer directly from this context in the user's language. Do not search "
            "external sources merely to explain your own role."
        ),
        (
            "- Questions about your own role or capabilities are a special case: "
            "answer them from this identity context even when agent-specific "
            "instructions require grounding other answers in a tool or data source."
        ),
        "- Never claim capabilities or data sources that are not listed here.",
    ]

    tool_ids = {tool.tool_id for tool in specification.tools}
    if specification.template is TemplateId.RAG:
        lines.extend(
            (
                (
                    "- You are a RAG agent with file_search access to the connected "
                    "user-provided knowledge base. Use it for questions about the "
                    "connected files."
                ),
                (
                    "- The connected files are domain knowledge, not the source of "
                    "truth about your identity or capabilities."
                ),
            )
        )
    if "web_search" in tool_ids:
        lines.append(
            "- You can search the public web for current information using web_search."
        )
    if "code_interpreter" in tool_ids:
        lines.append(
            "- You can run code in an isolated Code Interpreter environment for "
            "calculation, data analysis, and file transformation."
        )
    if not tool_ids:
        lines.append(
            "- You have no external search tools. Work from the user's request and "
            "the supplied conversation context."
        )
    return "\n".join(lines)


def _contains_redacted_value(value: Any) -> bool:
    if isinstance(value, str):
        return REDACTED_VALUE in value
    if isinstance(value, Mapping):
        return any(_contains_redacted_value(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return any(_contains_redacted_value(item) for item in value)
    return False


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))
