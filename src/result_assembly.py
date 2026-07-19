import io
import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal, TypeAlias

from openai.types.responses import ResponseTextDeltaEvent

from context import ConversationOptions


@dataclass(frozen=True)
class ToolExecution:
    call_id: str
    name: str
    arguments: dict[str, Any]
    output: Any = None


@dataclass(frozen=True)
class AgentRunResult:
    text: str
    tool_executions: tuple[ToolExecution, ...] = ()


@dataclass(frozen=True)
class IndexedFileResult:
    filename: str
    file_id: str


@dataclass(frozen=True)
class MarkdownResultPart:
    text: str
    kind: Literal["markdown"] = field(init=False, default="markdown")


@dataclass(frozen=True)
class VectorIndexResultPart:
    index_name: str
    index_id: str
    files: tuple[IndexedFileResult, ...]
    expires_after_days: int
    kind: Literal["vector_index"] = field(init=False, default="vector_index")


ResultPart: TypeAlias = MarkdownResultPart | VectorIndexResultPart


class AgentRunCollector:
    """Collects user-facing text and authoritative function-tool results."""

    def __init__(self) -> None:
        self._text = io.StringIO()
        self._calls: dict[str, ToolExecution] = {}
        self._call_order: list[str] = []
        self._anonymous_call_number = 0

    def consume(self, event: Any) -> None:
        if event.type == "raw_response_event" and isinstance(
            event.data, ResponseTextDeltaEvent
        ):
            self._text.write(event.data.delta)
            return
        if event.type != "run_item_stream_event":
            return
        if event.name == "tool_called":
            self._consume_tool_call(event.item)
        elif event.name == "tool_output":
            self._consume_tool_output(event.item)

    def build(self) -> AgentRunResult:
        return AgentRunResult(
            text=self._text.getvalue(),
            tool_executions=tuple(self._calls[key] for key in self._call_order),
        )

    def _consume_tool_call(self, item: Any) -> None:
        raw_item = item.raw_item
        call_id = self._value(raw_item, "call_id") or self._value(raw_item, "id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"anonymous-{self._anonymous_call_number}"
            self._anonymous_call_number += 1
        name = self._value(raw_item, "name")
        if not isinstance(name, str) or not name:
            return
        arguments = self._parse_arguments(self._value(raw_item, "arguments"))
        if call_id not in self._calls:
            self._call_order.append(call_id)
        self._calls[call_id] = ToolExecution(
            call_id=call_id,
            name=name,
            arguments=arguments,
        )

    def _consume_tool_output(self, item: Any) -> None:
        raw_item = item.raw_item
        call_id = self._value(raw_item, "call_id") or self._value(raw_item, "id")
        if not isinstance(call_id, str) or call_id not in self._calls:
            return
        self._calls[call_id] = replace(
            self._calls[call_id],
            output=item.output,
        )

    @staticmethod
    def _parse_arguments(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if not isinstance(value, str):
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}

    @staticmethod
    def _value(source: Any, name: str) -> Any:
        if isinstance(source, Mapping):
            return source.get(name)
        return getattr(source, name, None)


class ResultAssembler:
    def assemble(
        self,
        run: AgentRunResult,
        responded_by: ConversationOptions,
        filenames_by_file_id: Mapping[str, str],
    ) -> tuple[ResultPart, ...]:
        parts: list[ResultPart] = []
        if responded_by is ConversationOptions.RAG:
            parts.extend(
                self._vector_index_parts(run.tool_executions, filenames_by_file_id)
            )
        if run.text.strip():
            parts.append(MarkdownResultPart(text=run.text))
        return tuple(parts)

    @staticmethod
    def _vector_index_parts(
        tool_executions: tuple[ToolExecution, ...],
        filenames_by_file_id: Mapping[str, str],
    ) -> list[VectorIndexResultPart]:
        parts: list[VectorIndexResultPart] = []
        seen_index_ids: set[str] = set()
        for execution in tool_executions:
            if execution.name != "create_search_index":
                continue
            index_id = execution.output
            index_name = execution.arguments.get("vector_store_name")
            file_ids = execution.arguments.get("file_ids")
            if (
                not isinstance(index_id, str)
                or not index_id
                or not isinstance(index_name, str)
                or not isinstance(file_ids, list)
                or index_id in seen_index_ids
            ):
                continue
            files = tuple(
                IndexedFileResult(
                    filename=filenames_by_file_id.get(file_id, file_id),
                    file_id=file_id,
                )
                for file_id in file_ids
                if isinstance(file_id, str)
            )
            parts.append(
                VectorIndexResultPart(
                    index_name=index_name,
                    index_id=index_id,
                    files=files,
                    expires_after_days=1,
                )
            )
            seen_index_ids.add(index_id)
        return parts


def merge_agent_runs(
    *runs: AgentRunResult, text_from_last: bool = True
) -> AgentRunResult:
    if not runs:
        return AgentRunResult(text="")
    text = runs[-1].text if text_from_last else "".join(run.text for run in runs)
    return AgentRunResult(
        text=text,
        tool_executions=tuple(
            execution for run in runs for execution in run.tool_executions
        ),
    )


def result_part_to_record(part: ResultPart) -> dict[str, Any]:
    if isinstance(part, MarkdownResultPart):
        return {"kind": part.kind, "text": part.text}
    return {
        "kind": part.kind,
        "index_name": part.index_name,
        "index_id": part.index_id,
        "expires_after_days": part.expires_after_days,
        "files": [
            {"filename": file.filename, "file_id": file.file_id} for file in part.files
        ],
    }


def render_result_text(parts: tuple[ResultPart, ...]) -> str:
    sections: list[str] = []
    for part in parts:
        if isinstance(part, MarkdownResultPart):
            sections.append(part.text.strip())
            continue
        lines = [
            "Созданный векторный индекс",
            f"Имя индекса: {part.index_name}",
            f"ID индекса: {part.index_id}",
        ]
        if part.files:
            lines.append("Файлы в индексе:")
            lines.extend(
                f"{number}. {file.filename} (file_id: {file.file_id})"
                for number, file in enumerate(part.files, start=1)
            )
        lines.append(
            "Индекс автоматически удаляется через "
            f"{part.expires_after_days} день после последней активности."
        )
        sections.append("\n".join(lines))
    return "\n\n".join(section for section in sections if section)
