import json
import logging
from types import SimpleNamespace

from agent_specification import build_one_prompt_specification
from context import ConversationOptions
from result_assembly import (
    AgentSpecificationResultPart,
    AgentRunCollector,
    AgentRunResult,
    IndexedFileResult,
    MarkdownResultPart,
    ResultAssembler,
    ToolExecution,
    VectorIndexResultPart,
    merge_agent_runs,
    render_result_text,
    result_part_to_record,
)


def test_collector_pairs_tool_call_with_its_authoritative_output() -> None:
    collector = AgentRunCollector()
    collector.consume(
        SimpleNamespace(
            type="run_item_stream_event",
            name="tool_called",
            item=SimpleNamespace(
                raw_item={
                    "call_id": "call-1",
                    "name": "create_search_index",
                    "arguments": (
                        '{"file_ids":["file-1"],"vector_store_name":"knowledge"}'
                    ),
                }
            ),
        )
    )
    collector.consume(
        SimpleNamespace(
            type="run_item_stream_event",
            name="tool_output",
            item=SimpleNamespace(
                raw_item={"call_id": "call-1"},
                output="index-1",
            ),
        )
    )

    run = collector.build()

    assert run.tool_executions == (
        ToolExecution(
            call_id="call-1",
            name="create_search_index",
            arguments={
                "file_ids": ["file-1"],
                "vector_store_name": "knowledge",
            },
            output="index-1",
        ),
    )


def test_rag_result_contains_typed_index_and_model_markdown() -> None:
    run = AgentRunResult(
        text="## Сгенерированный system-prompt\n\nТекст промпта",
        tool_executions=(
            ToolExecution(
                call_id="call-1",
                name="create_search_index",
                arguments={
                    "file_ids": ["file-1", "file-2"],
                    "vector_store_name": "knowledge",
                },
                output="index-1",
            ),
        ),
    )

    parts = ResultAssembler().assemble(
        run,
        ConversationOptions.RAG,
        {"file-1": "guide.pdf", "file-2": "faq.txt"},
    )

    assert parts[0] == VectorIndexResultPart(
        index_name="knowledge",
        index_id="index-1",
        files=(
            IndexedFileResult("guide.pdf", "file-1"),
            IndexedFileResult("faq.txt", "file-2"),
        ),
        expires_after_days=1,
    )
    assert parts[1] == MarkdownResultPart(text=run.text)
    assert result_part_to_record(parts[0])["kind"] == "vector_index"
    rendered = render_result_text(parts)
    assert "ID индекса: index-1" in rendered
    assert "1. guide.pdf (file_id: file-1)" in rendered
    assert "Текст промпта" in rendered


def test_ready_finalization_adds_typed_agent_specification() -> None:
    specification = build_one_prompt_specification(
        purpose="Draft support replies",
        instructions="Be concise and do not invent facts.",
        expected_result="Reusable support-agent specification",
        web_search=True,
    )
    run = AgentRunResult(
        text="Спецификация готова.",
        tool_executions=(
            ToolExecution(
                call_id="call-spec",
                name="finalize_agent_specification",
                arguments={},
                output=json.dumps({"status": "ready"}),
            ),
        ),
    )

    parts = ResultAssembler().assemble(
        run,
        ConversationOptions.ONE_PROMPT,
        {},
        specification=specification,
    )

    assert isinstance(parts[0], AgentSpecificationResultPart)
    assert parts[0].specification.status == "ready"
    assert result_part_to_record(parts[0])["specification"]["purpose"] == (
        "Draft support replies"
    )
    assert result_part_to_record(parts[0])["specification"]["tools"] == [
        {
            "description": "Searches the public web for current information.",
            "parameters": {"search_context_size": "medium"},
            "title": "Web search",
            "tool_id": "web_search",
        }
    ]


def test_incomplete_or_unconfirmed_specification_is_not_exported() -> None:
    incomplete = build_one_prompt_specification(
        purpose="",
        instructions="",
        expected_result="",
    )
    run = AgentRunResult(
        text="Уточните назначение.",
        tool_executions=(
            ToolExecution(
                call_id="call-spec",
                name="finalize_agent_specification",
                arguments={},
                output='{"ready": false}',
            ),
        ),
    )

    parts = ResultAssembler().assemble(
        run,
        ConversationOptions.ONE_PROMPT,
        {},
        specification=incomplete,
    )

    assert parts == (MarkdownResultPart(text="Уточните назначение."),)


def test_update_after_ready_finalization_invalidates_result_export() -> None:
    specification = build_one_prompt_specification(
        purpose="Draft revised support replies",
        instructions="Be concise.",
        expected_result="Reusable support-agent specification",
    )
    run = AgentRunResult(
        text="Спецификация изменена и требует повторной финализации.",
        tool_executions=(
            ToolExecution(
                call_id="call-finalize",
                name="finalize_agent_specification",
                arguments={},
                output=json.dumps({"status": "ready"}),
            ),
            ToolExecution(
                call_id="call-update",
                name="update_agent_specification",
                arguments={"purpose": "Draft revised support replies"},
                output=json.dumps({"status": "ready"}),
            ),
        ),
    )

    parts = ResultAssembler().assemble(
        run,
        ConversationOptions.ONE_PROMPT,
        {},
        specification=specification,
    )

    assert parts == (
        MarkdownResultPart(
            text="Спецификация изменена и требует повторной финализации."
        ),
    )


def test_merged_run_keeps_tool_facts_and_uses_last_agent_text() -> None:
    coordinator = AgentRunResult(
        text="TASK DELEGATED",
        tool_executions=(ToolExecution("route", "delegate_rag", {}, "TASK DELEGATED"),),
    )
    rag = AgentRunResult(text="Готово")

    merged = merge_agent_runs(coordinator, rag)

    assert merged.text == "Готово"
    assert merged.tool_executions == coordinator.tool_executions


def test_collector_reports_malformed_tool_arguments(
    caplog,
) -> None:
    collector = AgentRunCollector()

    with caplog.at_level(logging.WARNING):
        collector.consume(
            SimpleNamespace(
                type="run_item_stream_event",
                name="tool_called",
                item=SimpleNamespace(
                    raw_item={
                        "call_id": "call-bad",
                        "name": "create_search_index",
                        "arguments": "{broken-json",
                    }
                ),
            )
        )

    assert collector.build().tool_executions[0].arguments == {}
    assert "Malformed tool arguments" in caplog.text
