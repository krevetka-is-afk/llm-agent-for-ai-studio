from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
import re
from typing import Any

from .catalog import (
    TemplateId,
    component_descriptor,
    is_public_application_tool,
    template_descriptor,
    template_required_fields,
)


SCHEMA_VERSION = "1.0"
TOP_LEVEL_RECORD_FIELDS = frozenset(
    {
        "schema_version",
        "agent_type",
        "template",
        "purpose",
        "audience",
        "inputs",
        "instructions",
        "constraints",
        "knowledge_sources",
        "tools",
        "expected_result",
        "parameters",
        "status",
        "validation",
    }
)
KNOWLEDGE_SOURCE_RECORD_FIELDS = frozenset({"source_id", "title", "kind", "reference"})
TOOL_RECORD_FIELDS = frozenset({"tool_id", "title", "description", "parameters"})
VALIDATION_RECORD_FIELDS = frozenset({"status", "missing_fields", "issues"})
VALIDATION_ISSUE_RECORD_FIELDS = frozenset({"field", "message"})
WEB_SEARCH_CONTEXT_SIZES = frozenset({"low", "medium", "high"})
SECRET_FIELD_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "oauth",
    "password",
    "secret",
    "token",
)
SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(?P<label>api[_ -]?key|access[_ -]?token|refresh[_ -]?token|"
    r"token|password|secret|oauth|authorization)\b"
    r"(?P<separator>\s*(?:=|:)\s*)"
    r"(?P<value>[^\s,;]{4,})"
)
BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}")
KNOWN_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b"),
    re.compile(r"\bAQ[A-Za-z0-9_-]{6,}\b"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
        r"-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
)


class AgentSpecificationStatus(StrEnum):
    DRAFT = "draft"
    NEEDS_CLARIFICATION = "needs_clarification"
    READY = "ready"


class InvalidSpecificationRecordError(ValueError):
    """Raised when serialized specification data violates the schema contract."""


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str

    def to_record(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


@dataclass(frozen=True)
class ValidationResult:
    status: AgentSpecificationStatus
    missing_fields: tuple[str, ...] = ()
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def is_ready(self) -> bool:
        return self.status is AgentSpecificationStatus.READY

    def to_record(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "missing_fields": list(self.missing_fields),
            "issues": [issue.to_record() for issue in self.issues],
        }


@dataclass(frozen=True)
class KnowledgeSource:
    source_id: str
    title: str
    kind: str
    reference: str | None = None

    def to_record(self) -> dict[str, Any]:
        record = {
            "source_id": _redact_secret_text(self.source_id),
            "title": _redact_secret_text(self.title),
            "kind": _redact_secret_text(self.kind),
        }
        if self.reference is not None:
            record["reference"] = _redact_secret_text(self.reference)
        return record


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    title: str
    description: str
    parameters: Mapping[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "tool_id": _redact_secret_text(self.tool_id),
            "title": _redact_secret_text(self.title),
            "description": _redact_secret_text(self.description),
            "parameters": _json_safe_mapping(self.parameters),
        }


@dataclass(frozen=True)
class AgentSpecification:
    template: TemplateId
    purpose: str = ""
    audience: str = ""
    inputs: tuple[str, ...] = ()
    instructions: str = ""
    constraints: tuple[str, ...] = ()
    knowledge_sources: tuple[KnowledgeSource, ...] = ()
    tools: tuple[ToolDescriptor, ...] = ()
    expected_result: str = ""
    parameters: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    status: AgentSpecificationStatus = AgentSpecificationStatus.DRAFT

    @property
    def agent_type(self) -> str:
        return self.template.value

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return self.validate().missing_fields

    def validate(self) -> ValidationResult:
        missing_fields = tuple(
            field_name
            for field_name in template_required_fields(self.template)
            if not self._has_required_value(field_name)
        )
        issues = (*self._component_issues(), *self._secret_issues())
        if missing_fields or issues:
            return ValidationResult(
                status=AgentSpecificationStatus.NEEDS_CLARIFICATION,
                missing_fields=missing_fields,
                issues=issues,
            )
        return ValidationResult(status=AgentSpecificationStatus.READY)

    def with_validation_status(self) -> "AgentSpecification":
        return replace(self, status=self.validate().status)

    def to_record(self, *, include_validation: bool = True) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema_version": self.schema_version,
            "agent_type": self.agent_type,
            "template": self.template.value,
            "purpose": _redact_secret_text(self.purpose),
            "audience": _redact_secret_text(self.audience),
            "inputs": [_redact_secret_text(value) for value in self.inputs],
            "instructions": _redact_secret_text(self.instructions),
            "constraints": [_redact_secret_text(value) for value in self.constraints],
            "knowledge_sources": [
                source.to_record() for source in self.knowledge_sources
            ],
            "tools": [tool.to_record() for tool in self.tools],
            "expected_result": _redact_secret_text(self.expected_result),
            "parameters": _json_safe_mapping(self.parameters),
            "status": self.with_validation_status().status.value,
        }
        if include_validation:
            record["validation"] = self.validate().to_record()
        return record

    def to_dict(self) -> dict[str, Any]:
        return self.to_record()

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "AgentSpecification":
        _require_record_fields(
            record,
            allowed=TOP_LEVEL_RECORD_FIELDS,
            required=TOP_LEVEL_RECORD_FIELDS,
            path="specification",
        )
        schema_version = _require_record_string(
            record, "schema_version", path="specification"
        )
        if schema_version != SCHEMA_VERSION:
            raise InvalidSpecificationRecordError(
                f"Unsupported specification schema version: {schema_version!r}"
            )

        template_value = _require_record_string(
            record, "template", path="specification"
        )
        try:
            template = TemplateId(template_value)
        except ValueError as exc:
            raise InvalidSpecificationRecordError(
                f"Unknown specification template: {template_value!r}"
            ) from exc
        agent_type = _require_record_string(record, "agent_type", path="specification")
        if agent_type != template.value:
            raise InvalidSpecificationRecordError(
                "specification.agent_type must match specification.template"
            )

        status = _parse_status(
            _require_record_string(record, "status", path="specification"),
            path="specification.status",
        )
        serialized_validation = _parse_validation_record(
            _require_record_mapping(record, "validation", path="specification")
        )
        specification = cls(
            template=template,
            purpose=_require_record_string(record, "purpose", path="specification"),
            audience=_require_record_string(record, "audience", path="specification"),
            inputs=_require_record_string_list(record, "inputs", path="specification"),
            instructions=_require_record_string(
                record, "instructions", path="specification"
            ),
            constraints=_require_record_string_list(
                record, "constraints", path="specification"
            ),
            knowledge_sources=_parse_knowledge_sources(
                _require_record_list(record, "knowledge_sources", path="specification")
            ),
            tools=_parse_tools(
                _require_record_list(record, "tools", path="specification")
            ),
            expected_result=_require_record_string(
                record, "expected_result", path="specification"
            ),
            parameters=_require_json_mapping(
                record, "parameters", path="specification"
            ),
            schema_version=schema_version,
            status=status,
        )
        recomputed_validation = specification.validate()
        if (
            status is not recomputed_validation.status
            or serialized_validation != recomputed_validation
        ):
            raise InvalidSpecificationRecordError(
                "Serialized status or validation does not match recomputed validation"
            )
        return specification

    def _has_required_value(self, field_name: str) -> bool:
        if field_name == "purpose":
            return _has_text(self.purpose)
        if field_name == "instructions":
            return _has_text(self.instructions)
        if field_name == "expected_result":
            return _has_text(self.expected_result)
        if field_name == "knowledge_sources":
            return bool(self.knowledge_sources)
        if field_name == "tools":
            required_tool = (
                "knowledge_search" if self.template is TemplateId.RAG else None
            )
            if required_tool is None:
                return any(
                    is_public_application_tool(tool.tool_id) for tool in self.tools
                )
            return any(tool.tool_id == required_tool for tool in self.tools)
        if field_name.startswith("parameters."):
            _, key = field_name.split(".", maxsplit=1)
            return _has_value(self.parameters.get(key))
        raise ValueError(f"Unknown required specification field: {field_name}")

    def _component_issues(self) -> tuple[ValidationIssue, ...]:
        issues: list[ValidationIssue] = []
        allowed_components = set(template_descriptor(self.template).components)
        for tool in self.tools:
            if not is_public_application_tool(tool.tool_id):
                issues.append(
                    ValidationIssue(
                        field=f"tools.{tool.tool_id}",
                        message="Tool is not a public application tool",
                    )
                )
                continue
            if tool.tool_id not in allowed_components:
                issues.append(
                    ValidationIssue(
                        field=f"tools.{tool.tool_id}",
                        message="Tool is not supported by the selected template",
                    )
                )
                continue
            if tool.tool_id == "web_search":
                search_context_size = tool.parameters.get("search_context_size")
                if search_context_size not in WEB_SEARCH_CONTEXT_SIZES:
                    issues.append(
                        ValidationIssue(
                            field="tools.web_search.parameters.search_context_size",
                            message=(
                                "Web search context size must be low, medium, or high"
                            ),
                        )
                    )
            if tool.tool_id == "knowledge_search":
                tool_index_id = tool.parameters.get("index_id")
                specification_index_id = self.parameters.get("index_id")
                if not _has_text_value(tool_index_id):
                    issues.append(
                        ValidationIssue(
                            field="tools.knowledge_search.parameters.index_id",
                            message="Knowledge search requires an index_id",
                        )
                    )
                elif tool_index_id != specification_index_id:
                    issues.append(
                        ValidationIssue(
                            field="tools.knowledge_search.parameters.index_id",
                            message=(
                                "Knowledge search index_id must match "
                                "specification.parameters.index_id"
                            ),
                        )
                    )
        if self.template is TemplateId.ONE_PROMPT and self.knowledge_sources:
            issues.append(
                ValidationIssue(
                    field="knowledge_sources",
                    message="One-prompt template must not require a knowledge base",
                )
            )
        return tuple(issues)

    def _secret_issues(self) -> tuple[ValidationIssue, ...]:
        raw_record = {
            "purpose": self.purpose,
            "audience": self.audience,
            "inputs": self.inputs,
            "instructions": self.instructions,
            "constraints": self.constraints,
            "knowledge_sources": tuple(
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "kind": source.kind,
                    "reference": source.reference,
                }
                for source in self.knowledge_sources
            ),
            "tools": tuple(
                {
                    "tool_id": tool.tool_id,
                    "title": tool.title,
                    "description": tool.description,
                    "parameters": tool.parameters,
                }
                for tool in self.tools
            ),
            "expected_result": self.expected_result,
            "parameters": self.parameters,
        }
        secret_paths = set(_secret_paths(raw_record, prefix=""))
        secret_paths.update(_secret_text_paths(raw_record, prefix=""))
        return tuple(
            ValidationIssue(
                field=field_path,
                message="Specification must not contain credentials or secrets",
            )
            for field_path in sorted(secret_paths)
        )


def build_one_prompt_specification(
    *,
    purpose: str,
    instructions: str,
    expected_result: str,
    audience: str = "",
    inputs: Sequence[str] = (),
    constraints: Sequence[str] = (),
    parameters: Mapping[str, Any] | None = None,
    web_search: bool = False,
) -> AgentSpecification:
    return AgentSpecification(
        template=TemplateId.ONE_PROMPT,
        purpose=purpose,
        audience=audience,
        inputs=tuple(inputs),
        instructions=instructions,
        constraints=tuple(constraints),
        tools=(build_web_search_tool_descriptor(),) if web_search else (),
        expected_result=expected_result,
        parameters=parameters or {},
    ).with_validation_status()


def build_web_search_tool_descriptor() -> ToolDescriptor:
    component = component_descriptor("web_search")
    return ToolDescriptor(
        tool_id=component.component_id,
        title=component.title,
        description=component.description,
        parameters=dict(component.parameters or {}),
    )


def build_rag_specification(
    *,
    purpose: str,
    instructions: str,
    expected_result: str,
    index_id: str,
    index_name: str,
    knowledge_sources: Sequence[KnowledgeSource],
    audience: str = "",
    inputs: Sequence[str] = (),
    constraints: Sequence[str] = (),
    ttl_days: int = 1,
) -> AgentSpecification:
    return AgentSpecification(
        template=TemplateId.RAG,
        purpose=purpose,
        audience=audience,
        inputs=tuple(inputs),
        instructions=instructions,
        constraints=tuple(constraints),
        knowledge_sources=tuple(knowledge_sources),
        tools=(
            ToolDescriptor(
                tool_id="knowledge_search",
                title="Knowledge search",
                description="Searches the connected AI Studio vector index.",
                parameters={"index_id": index_id, "index_name": index_name},
            ),
        ),
        expected_result=expected_result,
        parameters={
            "index_id": index_id,
            "index_name": index_name,
            "ttl_days": ttl_days,
        },
    ).with_validation_status()


def specification_template_for(state: Any) -> TemplateId:
    state_name = getattr(state, "name", "")
    if state_name == "RAG":
        return TemplateId.RAG
    return TemplateId.ONE_PROMPT


def _has_text(value: str) -> bool:
    return bool(value.strip())


def _has_text_value(value: Any) -> bool:
    return isinstance(value, str) and _has_text(value)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return _has_text(value)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return bool(value)
    return True


def _json_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: ("[REDACTED]" if _is_secret_key(key) else _json_safe(value[key]))
        for key in sorted(value)
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, str):
        return _redact_secret_text(value)
    return value


def _secret_paths(value: Mapping[str, Any], *, prefix: str) -> tuple[str, ...]:
    paths: list[str] = []
    for key, nested_value in value.items():
        field_path = f"{prefix}.{key}" if prefix else str(key)
        key_lower = str(key).lower()
        if _is_secret_key(key_lower):
            paths.append(field_path)
        paths.extend(_nested_secret_paths(nested_value, prefix=field_path))
    return tuple(paths)


def _nested_secret_paths(value: Any, *, prefix: str) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        return _secret_paths(value, prefix=prefix)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(
            path
            for index, item in enumerate(value)
            for path in _nested_secret_paths(item, prefix=f"{prefix}[{index}]")
        )
    return ()


def _secret_text_paths(value: Any, *, prefix: str) -> tuple[str, ...]:
    if isinstance(value, str):
        return (prefix,) if _contains_secret_text(value) else ()
    if isinstance(value, Mapping):
        return tuple(
            path
            for key, item in value.items()
            for path in _secret_text_paths(
                item,
                prefix=f"{prefix}.{key}" if prefix else str(key),
            )
        )
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return tuple(
            path
            for index, item in enumerate(value)
            for path in _secret_text_paths(item, prefix=f"{prefix}[{index}]")
        )
    return ()


def _contains_secret_text(value: str) -> bool:
    return _redact_secret_text(value) != value


def _redact_secret_text(value: str) -> str:
    redacted = BEARER_TOKEN_PATTERN.sub("Bearer [REDACTED]", value)
    for pattern in KNOWN_SECRET_VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    redacted = SECRET_ASSIGNMENT_PATTERN.sub(
        lambda match: f"{match.group('label')}{match.group('separator')}[REDACTED]",
        redacted,
    )
    return redacted


def _is_secret_key(key: str) -> bool:
    key_lower = str(key).lower()
    return any(fragment in key_lower for fragment in SECRET_FIELD_FRAGMENTS)


def _require_record_fields(
    record: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    required: frozenset[str],
    path: str,
) -> None:
    if not isinstance(record, Mapping):
        raise InvalidSpecificationRecordError(f"{path} must be an object")
    actual = set(record)
    non_string_keys = [key for key in actual if not isinstance(key, str)]
    if non_string_keys:
        raise InvalidSpecificationRecordError(f"{path} keys must be strings")
    unknown = actual - allowed
    if unknown:
        raise InvalidSpecificationRecordError(
            f"{path} contains unknown fields: {', '.join(sorted(unknown))}"
        )
    missing = required - actual
    if missing:
        raise InvalidSpecificationRecordError(
            f"{path} is missing fields: {', '.join(sorted(missing))}"
        )


def _require_record_string(record: Mapping[str, Any], key: str, *, path: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise InvalidSpecificationRecordError(f"{path}.{key} must be a string")
    return value


def _require_record_list(
    record: Mapping[str, Any], key: str, *, path: str
) -> list[Any]:
    value = record.get(key)
    if not isinstance(value, list):
        raise InvalidSpecificationRecordError(f"{path}.{key} must be an array")
    return value


def _require_record_mapping(
    record: Mapping[str, Any], key: str, *, path: str
) -> Mapping[str, Any]:
    value = record.get(key)
    if not isinstance(value, Mapping):
        raise InvalidSpecificationRecordError(f"{path}.{key} must be an object")
    return value


def _require_record_string_list(
    record: Mapping[str, Any], key: str, *, path: str
) -> tuple[str, ...]:
    values = _require_record_list(record, key, path=path)
    if not all(isinstance(value, str) for value in values):
        raise InvalidSpecificationRecordError(f"{path}.{key} must contain only strings")
    return tuple(values)


def _require_json_mapping(
    record: Mapping[str, Any], key: str, *, path: str
) -> dict[str, Any]:
    value = _require_record_mapping(record, key, path=path)
    _validate_json_value(value, path=f"{path}.{key}")
    return dict(value)


def _validate_json_value(value: Any, *, path: str) -> None:
    if value is None or isinstance(value, str | int | float | bool):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise InvalidSpecificationRecordError(
                    f"{path} object keys must be strings"
                )
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise InvalidSpecificationRecordError(f"{path} must contain only JSON values")


def _parse_knowledge_sources(values: list[Any]) -> tuple[KnowledgeSource, ...]:
    sources: list[KnowledgeSource] = []
    for index, value in enumerate(values):
        path = f"specification.knowledge_sources[{index}]"
        if not isinstance(value, Mapping):
            raise InvalidSpecificationRecordError(f"{path} must be an object")
        _require_record_fields(
            value,
            allowed=KNOWLEDGE_SOURCE_RECORD_FIELDS,
            required=frozenset({"source_id", "title", "kind"}),
            path=path,
        )
        reference = value.get("reference")
        if reference is not None and not isinstance(reference, str):
            raise InvalidSpecificationRecordError(
                f"{path}.reference must be a string or null"
            )
        sources.append(
            KnowledgeSource(
                source_id=_require_record_string(value, "source_id", path=path),
                title=_require_record_string(value, "title", path=path),
                kind=_require_record_string(value, "kind", path=path),
                reference=reference,
            )
        )
    return tuple(sources)


def _parse_tools(values: list[Any]) -> tuple[ToolDescriptor, ...]:
    tools: list[ToolDescriptor] = []
    for index, value in enumerate(values):
        path = f"specification.tools[{index}]"
        if not isinstance(value, Mapping):
            raise InvalidSpecificationRecordError(f"{path} must be an object")
        _require_record_fields(
            value,
            allowed=TOOL_RECORD_FIELDS,
            required=TOOL_RECORD_FIELDS,
            path=path,
        )
        tools.append(
            ToolDescriptor(
                tool_id=_require_record_string(value, "tool_id", path=path),
                title=_require_record_string(value, "title", path=path),
                description=_require_record_string(value, "description", path=path),
                parameters=_require_json_mapping(value, "parameters", path=path),
            )
        )
    return tuple(tools)


def _parse_validation_record(record: Mapping[str, Any]) -> ValidationResult:
    path = "specification.validation"
    _require_record_fields(
        record,
        allowed=VALIDATION_RECORD_FIELDS,
        required=VALIDATION_RECORD_FIELDS,
        path=path,
    )
    status = _parse_status(
        _require_record_string(record, "status", path=path),
        path=f"{path}.status",
    )
    missing_fields = _require_record_string_list(record, "missing_fields", path=path)
    issue_values = _require_record_list(record, "issues", path=path)
    issues: list[ValidationIssue] = []
    for index, value in enumerate(issue_values):
        issue_path = f"{path}.issues[{index}]"
        if not isinstance(value, Mapping):
            raise InvalidSpecificationRecordError(f"{issue_path} must be an object")
        _require_record_fields(
            value,
            allowed=VALIDATION_ISSUE_RECORD_FIELDS,
            required=VALIDATION_ISSUE_RECORD_FIELDS,
            path=issue_path,
        )
        issues.append(
            ValidationIssue(
                field=_require_record_string(value, "field", path=issue_path),
                message=_require_record_string(value, "message", path=issue_path),
            )
        )
    return ValidationResult(
        status=status,
        missing_fields=missing_fields,
        issues=tuple(issues),
    )


def _parse_status(value: str, *, path: str) -> AgentSpecificationStatus:
    try:
        return AgentSpecificationStatus(value)
    except ValueError as exc:
        raise InvalidSpecificationRecordError(
            f"{path} has unknown value: {value!r}"
        ) from exc
