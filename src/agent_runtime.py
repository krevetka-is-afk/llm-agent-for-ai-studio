import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from agent_specification import (
    SCHEMA_VERSION as SPECIFICATION_SCHEMA_VERSION,
    AgentSpecification,
    AgentSpecificationStatus,
)
from component_catalog import TemplateId
from config import AgentRuntimeConfig


RUNTIME_SCHEMA_VERSION = "1.0"
REDACTED_VALUE = "[REDACTED]"


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
    runtime: AgentRuntimeConfig,
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
