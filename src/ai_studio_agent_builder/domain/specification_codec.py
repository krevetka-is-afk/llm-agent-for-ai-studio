import json
from collections.abc import Mapping
from typing import Any

from .specification import (
    AgentSpecification,
    InvalidSpecificationRecordError,
)


class InvalidSpecificationJSONError(InvalidSpecificationRecordError):
    """Raised when a serialized specification is not strict UTF-8 JSON."""

    def __init__(
        self,
        message: str,
        *,
        lineno: int | None = None,
        colno: int | None = None,
    ) -> None:
        self.lineno = lineno
        self.colno = colno
        super().__init__(message)


class InvalidSpecificationRootError(InvalidSpecificationRecordError):
    """Raised when decoded JSON is not an object at the document root."""


def load_agent_specification(record: Any) -> AgentSpecification:
    """Validate a decoded JSON object and construct a domain specification."""
    if not isinstance(record, Mapping):
        raise InvalidSpecificationRootError("Specification JSON root must be an object")
    return AgentSpecification.from_record(record)


def loads_agent_specification(payload: str | bytes | bytearray) -> AgentSpecification:
    """Decode strict UTF-8 JSON and validate the AgentSpecification 1.0 schema."""
    if isinstance(payload, bytes | bytearray):
        try:
            text = bytes(payload).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidSpecificationJSONError(
                "Specification payload must be valid UTF-8 JSON"
            ) from exc
    else:
        text = payload

    try:
        record = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_reject_non_finite_number,
        )
    except json.JSONDecodeError as exc:
        raise InvalidSpecificationJSONError(
            "Specification payload contains invalid JSON",
            lineno=exc.lineno,
            colno=exc.colno,
        ) from exc
    return load_agent_specification(record)


def dump_agent_specification(
    specification: AgentSpecification,
    *,
    include_validation: bool = True,
) -> dict[str, Any]:
    """Return the canonical, secret-redacted AgentSpecification 1.0 record."""
    return specification.to_record(include_validation=include_validation)


def dumps_agent_specification(
    specification: AgentSpecification,
    *,
    include_validation: bool = True,
    indent: int | None = 2,
) -> str:
    """Serialize a specification as deterministic strict JSON."""
    return json.dumps(
        dump_agent_specification(
            specification,
            include_validation=include_validation,
        ),
        allow_nan=False,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
    )


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidSpecificationJSONError(
                f"Specification payload contains duplicate key: {key!r}"
            )
        result[key] = value
    return result


def _reject_non_finite_number(value: str) -> Any:
    raise InvalidSpecificationJSONError(
        f"Specification payload contains non-finite number: {value}"
    )


__all__ = [
    "InvalidSpecificationJSONError",
    "InvalidSpecificationRootError",
    "dump_agent_specification",
    "dumps_agent_specification",
    "load_agent_specification",
    "loads_agent_specification",
]
