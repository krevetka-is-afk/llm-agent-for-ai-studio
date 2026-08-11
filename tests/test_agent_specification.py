import json
from copy import deepcopy
from dataclasses import replace

import pytest

from ai_studio_agent_builder.domain.specification import (
    AgentSpecification,
    AgentSpecificationStatus,
    InvalidSpecificationRecordError,
    KnowledgeSource,
    ToolDescriptor,
    build_one_prompt_specification,
    build_rag_specification,
)
from ai_studio_agent_builder.domain.catalog import (
    ComponentKind,
    TemplateId,
    catalog_record,
    component_descriptor,
    is_public_application_tool,
    template_descriptor,
)


def test_empty_one_prompt_specification_reports_all_required_fields() -> None:
    spec = AgentSpecification(template=TemplateId.ONE_PROMPT)

    result = spec.validate()

    assert result.status is AgentSpecificationStatus.NEEDS_CLARIFICATION
    assert result.missing_fields == ("purpose", "instructions", "expected_result")
    assert spec.to_record()["status"] == "needs_clarification"


def test_complete_one_prompt_specification_is_ready_and_json_safe() -> None:
    spec = build_one_prompt_specification(
        purpose="Help support engineers draft concise answers",
        audience="Support team",
        inputs=("customer question",),
        instructions="Use a friendly tone and ask for logs when the issue is unclear.",
        constraints=("Do not invent product behavior.",),
        expected_result="A reusable support assistant system prompt",
        parameters={"temperature": 0.2, "labels": ("support", "drafting")},
    )

    record = spec.to_record()

    assert spec.status is AgentSpecificationStatus.READY
    assert spec.validate().is_ready
    assert record["agent_type"] == "one_prompt"
    assert record["template"] == "one_prompt"
    assert record["validation"]["missing_fields"] == []
    assert json.loads(json.dumps(record, ensure_ascii=False)) == record


def test_one_prompt_web_search_serializes_as_portable_tool_descriptor() -> None:
    spec = build_one_prompt_specification(
        purpose="Summarize current industry news",
        instructions="Search the web before answering.",
        expected_result="A current, source-grounded briefing",
        web_search=True,
    )

    record = spec.to_record()

    assert record["knowledge_sources"] == []
    assert record["tools"] == [
        {
            "tool_id": "web_search",
            "title": "Web search",
            "description": "Searches the public web for current information.",
            "parameters": {"search_context_size": "medium"},
        }
    ]


def test_ordinary_one_prompt_specification_has_no_tools() -> None:
    spec = build_one_prompt_specification(
        purpose="Rewrite support replies",
        instructions="Be concise.",
        expected_result="A reusable system prompt",
    )

    assert spec.tools == ()
    assert spec.to_record()["tools"] == []


def test_incomplete_rag_specification_requires_sources_tool_and_index() -> None:
    spec = AgentSpecification(
        template=TemplateId.RAG,
        purpose="Answer questions from internal docs",
        instructions="Search first, answer with citations.",
        expected_result="RAG assistant prompt and connected index",
    )

    result = spec.validate()

    assert result.status is AgentSpecificationStatus.NEEDS_CLARIFICATION
    assert result.missing_fields == (
        "knowledge_sources",
        "tools",
        "parameters.index_id",
    )


def test_complete_rag_specification_contains_public_knowledge_search_tool() -> None:
    spec = build_rag_specification(
        purpose="Answer onboarding questions from uploaded handbook",
        instructions="Use the connected vector index before answering.",
        expected_result="A RAG assistant with searchable handbook knowledge",
        index_id="vs-123",
        index_name="onboarding",
        knowledge_sources=(
            KnowledgeSource(
                source_id="file-1",
                title="handbook.pdf",
                kind="uploaded_file",
                reference="file-1",
            ),
        ),
    )

    record = spec.to_record()

    assert spec.validate().is_ready
    assert record["status"] == "ready"
    assert record["parameters"]["index_id"] == "vs-123"
    assert record["knowledge_sources"][0]["title"] == "handbook.pdf"
    assert record["tools"] == [
        {
            "tool_id": "knowledge_search",
            "title": "Knowledge search",
            "description": "Searches the connected AI Studio vector index.",
            "parameters": {"index_id": "vs-123", "index_name": "onboarding"},
        }
    ]


def test_rag_requires_knowledge_search_instead_of_any_public_tool() -> None:
    spec = AgentSpecification(
        template=TemplateId.RAG,
        purpose="Answer from documents",
        instructions="Search before answering.",
        expected_result="Grounded answer",
        knowledge_sources=(
            KnowledgeSource("file-1", "guide.pdf", "uploaded_file", "file-1"),
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
    )

    result = spec.validate()

    assert "tools" in result.missing_fields
    assert any(
        issue.field == "tools.web_search"
        and issue.message == "Tool is not supported by the selected template"
        for issue in result.issues
    )


def test_rag_requires_matching_tool_and_specification_index_ids() -> None:
    spec = build_rag_specification(
        purpose="Answer from documents",
        instructions="Search before answering.",
        expected_result="Grounded answer",
        index_id="vs-123",
        index_name="docs",
        knowledge_sources=(
            KnowledgeSource("file-1", "guide.pdf", "uploaded_file", "file-1"),
        ),
    )
    mismatched = replace(
        spec,
        tools=(
            ToolDescriptor(
                tool_id="knowledge_search",
                title="Knowledge search",
                description="Searches the index",
                parameters={"index_id": "vs-other"},
            ),
        ),
    )

    result = mismatched.validate()

    assert not result.is_ready
    assert result.issues[0].field == "tools.knowledge_search.parameters.index_id"


def test_web_search_rejects_unknown_context_size() -> None:
    spec = AgentSpecification(
        template=TemplateId.ONE_PROMPT,
        purpose="Summarize news",
        instructions="Search first.",
        expected_result="Briefing",
        tools=(
            ToolDescriptor(
                tool_id="web_search",
                title="Web search",
                description="Search the web",
                parameters={"search_context_size": "huge"},
            ),
        ),
        status=AgentSpecificationStatus.READY,
    )

    result = spec.validate()

    assert not result.is_ready
    assert result.issues[0].field == "tools.web_search.parameters.search_context_size"


def test_specification_record_round_trip_is_strict_and_lossless() -> None:
    original = build_rag_specification(
        purpose="Отвечать по внутренним документам",
        instructions="Сначала выполни поиск.",
        expected_result="Ответ со ссылками",
        index_id="vs-123",
        index_name="docs",
        knowledge_sources=(
            KnowledgeSource("file-1", "справочник.pdf", "uploaded_file", "file-1"),
        ),
        constraints=("Не выдумывай факты.",),
    )
    record = original.to_record()

    restored = AgentSpecification.from_record(record)

    assert restored == original
    assert restored.to_record() == record


@pytest.mark.parametrize(
    "mutation",
    [
        lambda record: record.update({"unexpected": True}),
        lambda record: record.update({"schema_version": "2.0"}),
        lambda record: record.update({"agent_type": "rag"}),
        lambda record: record.update({"status": "draft"}),
        lambda record: record["validation"].update({"status": "draft"}),
        lambda record: record["tools"][0].update({"unexpected": True}),
    ],
)
def test_specification_record_rejects_malformed_data(mutation) -> None:
    record = build_one_prompt_specification(
        purpose="Summarize news",
        instructions="Search first.",
        expected_result="Briefing",
        web_search=True,
    ).to_record()
    malformed = deepcopy(record)
    mutation(malformed)

    with pytest.raises(InvalidSpecificationRecordError):
        AgentSpecification.from_record(malformed)


def test_internal_tools_are_not_valid_created_agent_tools() -> None:
    spec = AgentSpecification(
        template=TemplateId.RAG,
        purpose="Answer from docs",
        instructions="Use the index.",
        expected_result="A RAG agent",
        knowledge_sources=(
            KnowledgeSource("file-1", "guide.pdf", "uploaded_file", "file-1"),
        ),
        tools=(
            ToolDescriptor(
                tool_id="finish_dialog",
                title="Finish dialog",
                description="Internal tool",
            ),
        ),
        parameters={"index_id": "vs-123"},
    )

    result = spec.validate()

    assert result.status is AgentSpecificationStatus.NEEDS_CLARIFICATION
    assert result.missing_fields == ("tools",)
    assert result.issues[0].field == "tools.finish_dialog"


def test_secret_like_parameters_are_reported_and_not_ready() -> None:
    spec = build_one_prompt_specification(
        purpose="Draft answers",
        instructions="Be concise.",
        expected_result="Prompt",
        parameters={"api_key": "AQAAAA-secret"},
    )

    result = spec.validate()

    assert not result.is_ready
    assert result.issues[0].field == "parameters.api_key"
    record = spec.to_record()
    assert record["status"] == "needs_clarification"
    assert record["parameters"]["api_key"] == "[REDACTED]"


def test_nested_secret_like_parameters_are_redacted_and_reported() -> None:
    spec = build_one_prompt_specification(
        purpose="Draft answers",
        instructions="Be concise.",
        expected_result="Prompt",
        parameters={"headers": [{"Authorization": "Bearer secret"}]},
    )

    result = spec.validate()
    record = spec.to_record()

    assert result.issues[0].field == "parameters.headers[0].Authorization"
    assert record["parameters"]["headers"][0]["Authorization"] == "[REDACTED]"


def test_secrets_in_free_text_fields_block_export_and_are_redacted() -> None:
    spec = build_one_prompt_specification(
        purpose="Draft answers",
        instructions="Use API key sk-test-secret when calling the service.",
        constraints=("Send authorization: Bearer abcdefgh123456.",),
        expected_result="Return password=hunter2 in the generated prompt.",
    )

    result = spec.validate()
    record = spec.to_record()

    assert not result.is_ready
    assert {issue.field for issue in result.issues} == {
        "constraints[0]",
        "expected_result",
        "instructions",
    }
    serialized = json.dumps(record, ensure_ascii=False)
    assert "sk-test-secret" not in serialized
    assert "abcdefgh123456" not in serialized
    assert "hunter2" not in serialized
    assert serialized.count("[REDACTED]") >= 3


def test_secrets_in_nested_components_block_export_and_are_redacted() -> None:
    spec = AgentSpecification(
        template=TemplateId.RAG,
        purpose="Answer from documents",
        instructions="Search the index before answering.",
        expected_result="A grounded answer",
        knowledge_sources=(
            KnowledgeSource(
                source_id="file-1",
                title="Source sk-source-secret",
                kind="uploaded_file",
                reference="password=source-password",
            ),
        ),
        tools=(
            ToolDescriptor(
                tool_id="knowledge_search",
                title="Knowledge search",
                description="Authorization: Bearer nestedtooltoken",
                parameters={
                    "index_id": "vs-123",
                    "api_key": "plain-secret-value",
                },
            ),
        ),
        parameters={"index_id": "vs-123"},
    )

    result = spec.validate()
    record = spec.to_record()

    assert not result.is_ready
    assert {issue.field for issue in result.issues} == {
        "knowledge_sources[0].reference",
        "knowledge_sources[0].title",
        "tools[0].description",
        "tools[0].parameters.api_key",
    }
    serialized = json.dumps(record, ensure_ascii=False)
    for secret in (
        "sk-source-secret",
        "source-password",
        "nestedtooltoken",
        "plain-secret-value",
    ):
        assert secret not in serialized


def test_catalog_separates_public_application_tools_from_internal_tools() -> None:
    one_prompt_template = template_descriptor(TemplateId.ONE_PROMPT)
    rag_template = template_descriptor(TemplateId.RAG)
    knowledge_search = component_descriptor("knowledge_search")
    web_search = component_descriptor("web_search")
    finish_dialog = component_descriptor("finish_dialog")

    assert rag_template.required_fields == (
        "purpose",
        "instructions",
        "expected_result",
        "knowledge_sources",
        "tools",
        "parameters.index_id",
    )
    assert "tools" in one_prompt_template.optional_fields
    assert "web_search" in one_prompt_template.components
    assert knowledge_search.kind is ComponentKind.APPLICATION_TOOL
    assert web_search.kind is ComponentKind.APPLICATION_TOOL
    assert web_search.parameters == {"search_context_size": "medium"}
    assert finish_dialog.kind is ComponentKind.INTERNAL_TOOL
    assert is_public_application_tool("knowledge_search")
    assert is_public_application_tool("web_search")
    assert not is_public_application_tool("finish_dialog")
    public_ids = {
        component["component_id"] for component in catalog_record()["components"]
    }
    assert "knowledge_search" in public_ids
    assert "web_search" in public_ids
    assert "finish_dialog" not in public_ids
