import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from ..domain.routing import ConversationOptions
from ..domain.specification import AgentSpecification


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


@dataclass(frozen=True)
class AgentSpecificationResultPart:
    specification: AgentSpecification
    kind: Literal["agent_specification"] = field(
        init=False, default="agent_specification"
    )


ResultPart: TypeAlias = (
    MarkdownResultPart | VectorIndexResultPart | AgentSpecificationResultPart
)


class ResultAssembler:
    def assemble(
        self,
        run: AgentRunResult,
        responded_by: ConversationOptions,
        filenames_by_file_id: Mapping[str, str],
        specification: AgentSpecification | None = None,
    ) -> tuple[ResultPart, ...]:
        parts: list[ResultPart] = []
        if responded_by is ConversationOptions.RAG:
            parts.extend(
                self._vector_index_parts(run.tool_executions, filenames_by_file_id)
            )
        if specification is not None and self._has_ready_finalization(
            run.tool_executions
        ):
            validated_specification = specification.with_validation_status()
            if validated_specification.validate().is_ready:
                parts.append(
                    AgentSpecificationResultPart(
                        specification=validated_specification,
                    )
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
            output = execution.output
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    continue
            if not isinstance(output, Mapping) or output.get("status") != "created":
                continue
            index_id = output.get("index_id")
            index_name = output.get("index_name")
            file_ids = output.get("file_ids")
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

    @staticmethod
    def _has_ready_finalization(
        tool_executions: tuple[ToolExecution, ...],
    ) -> bool:
        is_ready = False
        for execution in tool_executions:
            if execution.name == "update_agent_specification":
                is_ready = False
                continue
            if execution.name != "finalize_agent_specification":
                continue
            output = execution.output
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    is_ready = False
                    continue
            if isinstance(output, Mapping):
                is_ready = (
                    output.get("ready") is True or output.get("status") == "ready"
                )
            else:
                is_ready = False
        return is_ready


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
    if isinstance(part, AgentSpecificationResultPart):
        return {
            "kind": part.kind,
            "specification": part.specification.to_record(),
        }
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
        if isinstance(part, AgentSpecificationResultPart):
            spec = part.specification
            lines = [
                "Спецификация агента",
                f"Шаблон: {spec.template.value}",
                f"Статус: {spec.status.value}",
            ]
            if spec.missing_fields:
                lines.append("Недостающие поля: " + ", ".join(spec.missing_fields))
            sections.append("\n".join(lines))
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


__all__ = [
    "AgentRunResult",
    "AgentSpecificationResultPart",
    "IndexedFileResult",
    "MarkdownResultPart",
    "ResultAssembler",
    "ResultPart",
    "ToolExecution",
    "VectorIndexResultPart",
    "merge_agent_runs",
    "render_result_text",
    "result_part_to_record",
]
