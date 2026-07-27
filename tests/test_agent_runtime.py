import json
from dataclasses import replace

import pytest

from agent_runtime import (
    MissingRuntimeParameterError,
    SpecificationNotReadyError,
    UnsupportedAgentToolError,
    UnsupportedSpecificationVersionError,
    compile_agent_specification,
)
from agent_specification import (
    AgentSpecification,
    AgentSpecificationStatus,
    KnowledgeSource,
    ToolDescriptor,
    build_one_prompt_specification,
    build_rag_specification,
)
from component_catalog import TemplateId
from config import AgentRuntimeConfig


RUNTIME = AgentRuntimeConfig(
    model_name="gpt-oss-120b",
    temperature=0.3,
    max_output_tokens=900,
)


def test_compile_one_prompt_without_tools() -> None:
    specification = build_one_prompt_specification(
        purpose="Draft support replies",
        instructions="Answer concisely.",
        constraints=("Do not invent facts.", "Use plain language."),
        expected_result="A concise support reply",
    )

    config = compile_agent_specification(specification, runtime=RUNTIME)

    assert config.model_name == "gpt-oss-120b"
    assert config.tools == ()
    assert config.temperature == 0.3
    assert config.max_output_tokens == 900
    assert config.instructions == (
        "Agent identity and capabilities:\n"
        "- You are an AI agent configured for this purpose: Draft support replies\n"
        "- Treat this purpose, these system instructions, and the capabilities "
        "listed here as authoritative context about your role.\n"
        "- When the user asks who you are, what you can do, or how you work, "
        "answer directly from this context in the user's language. Do not search "
        "external sources merely to explain your own role.\n"
        "- Questions about your own role or capabilities are a special case: "
        "answer them from this identity context even when agent-specific "
        "instructions require grounding other answers in a tool or data source.\n"
        "- Never claim capabilities or data sources that are not listed here.\n"
        "- You have no external search tools. Work from the user's request and "
        "the supplied conversation context.\n\n"
        "Answer concisely.\n\n"
        "Constraints:\n"
        "- Do not invent facts.\n"
        "- Use plain language.\n\n"
        "Expected result:\n"
        "A concise support reply"
    )


def test_compile_web_search_to_native_tool() -> None:
    specification = build_one_prompt_specification(
        purpose="Summarize current news",
        instructions="Search before answering.",
        expected_result="A source-grounded briefing",
        web_search=True,
    )

    config = compile_agent_specification(specification, runtime=RUNTIME)

    assert config.tools == ({"type": "web_search", "search_context_size": "medium"},)
    assert (
        "You can search the public web for current information using web_search."
        in config.instructions
    )
    assert "Summarize current news" in config.instructions


def test_compile_rag_to_file_search() -> None:
    specification = build_rag_specification(
        purpose="Answer from the handbook",
        instructions="Search the handbook before answering.",
        expected_result="A grounded answer",
        index_id="vs-123",
        index_name="handbook",
        knowledge_sources=(
            KnowledgeSource("file-1", "handbook.pdf", "uploaded_file", "file-1"),
        ),
    )

    config = compile_agent_specification(specification, runtime=RUNTIME)

    assert config.tools == ({"type": "file_search", "vector_store_ids": ["vs-123"]},)
    assert "You are a RAG agent" in config.instructions
    assert "connected user-provided knowledge base" in config.instructions
    assert (
        "The connected files are domain knowledge, not the source of truth about "
        "your identity or capabilities." in config.instructions
    )
    assert "Answer from the handbook" in config.instructions


def test_compile_rejects_non_ready_specification() -> None:
    specification = AgentSpecification(
        template=TemplateId.ONE_PROMPT,
        purpose="Draft replies",
    )

    with pytest.raises(SpecificationNotReadyError):
        compile_agent_specification(specification, runtime=RUNTIME)


def test_compile_rejects_missing_rag_index_before_network() -> None:
    specification = AgentSpecification(
        template=TemplateId.RAG,
        purpose="Answer from documents",
        instructions="Search first.",
        expected_result="Answer",
        knowledge_sources=(
            KnowledgeSource("file-1", "handbook.pdf", "uploaded_file", "file-1"),
        ),
        tools=(
            ToolDescriptor(
                tool_id="knowledge_search",
                title="Knowledge search",
                description="Search",
                parameters={},
            ),
        ),
        parameters={},
        status=AgentSpecificationStatus.READY,
    )

    with pytest.raises(MissingRuntimeParameterError):
        compile_agent_specification(specification, runtime=RUNTIME)


def test_compile_rejects_unknown_or_internal_tool() -> None:
    specification = AgentSpecification(
        template=TemplateId.ONE_PROMPT,
        purpose="Draft replies",
        instructions="Be concise.",
        expected_result="Reply",
        tools=(
            ToolDescriptor(
                tool_id="finish_dialog",
                title="Finish",
                description="Internal tool",
            ),
        ),
        status=AgentSpecificationStatus.READY,
    )

    with pytest.raises(UnsupportedAgentToolError):
        compile_agent_specification(specification, runtime=RUNTIME)


def test_compile_rejects_template_tool_mismatch() -> None:
    specification = AgentSpecification(
        template=TemplateId.RAG,
        purpose="Answer from docs",
        instructions="Search first.",
        expected_result="Answer",
        knowledge_sources=(
            KnowledgeSource("file-1", "handbook.pdf", "uploaded_file", "file-1"),
        ),
        tools=(
            ToolDescriptor(
                tool_id="web_search",
                title="Web search",
                description="Search the web",
                parameters={"search_context_size": "medium"},
            ),
        ),
        parameters={"index_id": "vs-123"},
        status=AgentSpecificationStatus.READY,
    )

    with pytest.raises(SpecificationNotReadyError):
        compile_agent_specification(specification, runtime=RUNTIME)


def test_compile_rejects_mismatched_rag_index_ids() -> None:
    specification = build_rag_specification(
        purpose="Answer from docs",
        instructions="Search first.",
        expected_result="Answer",
        index_id="vs-123",
        index_name="docs",
        knowledge_sources=(
            KnowledgeSource("file-1", "handbook.pdf", "uploaded_file", "file-1"),
        ),
    )
    specification = replace(
        specification,
        tools=(
            replace(
                specification.tools[0],
                parameters={"index_id": "vs-other", "index_name": "docs"},
            ),
        ),
    )

    with pytest.raises(SpecificationNotReadyError):
        compile_agent_specification(specification, runtime=RUNTIME)


def test_compile_rejects_redacted_runtime_values() -> None:
    specification = AgentSpecification(
        template=TemplateId.ONE_PROMPT,
        purpose="Draft replies",
        instructions="Use [REDACTED] as the source.",
        expected_result="Reply",
        status=AgentSpecificationStatus.READY,
    )

    with pytest.raises(MissingRuntimeParameterError):
        compile_agent_specification(specification, runtime=RUNTIME)


def test_compile_rejects_unknown_schema_version() -> None:
    specification = replace(
        build_one_prompt_specification(
            purpose="Draft replies",
            instructions="Be concise.",
            expected_result="Reply",
        ),
        schema_version="2.0",
    )

    with pytest.raises(UnsupportedSpecificationVersionError):
        compile_agent_specification(specification, runtime=RUNTIME)


def test_runtime_json_is_canonical_and_unicode_safe() -> None:
    specification = build_one_prompt_specification(
        purpose="Писать ответы",
        instructions="Отвечай кратко.",
        expected_result="Краткий ответ",
    )
    original = specification.to_record()

    config = compile_agent_specification(specification, runtime=RUNTIME)

    assert json.loads(config.to_json()) == config.to_record()
    assert "Отвечай кратко." in config.to_json()
    assert specification.to_record() == original
