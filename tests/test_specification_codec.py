import json

import pytest

from ai_studio_agent_builder.domain.specification import build_one_prompt_specification
from ai_studio_agent_builder.domain.specification_codec import (
    InvalidSpecificationJSONError,
    InvalidSpecificationRootError,
    dumps_agent_specification,
    load_agent_specification,
    loads_agent_specification,
)


def _specification():
    return build_one_prompt_specification(
        purpose="Summarize support requests",
        instructions="Return a concise summary.",
        expected_result="A short summary",
    )


def test_codec_round_trips_canonical_strict_json() -> None:
    specification = _specification()

    payload = dumps_agent_specification(specification)
    restored = loads_agent_specification(payload.encode("utf-8"))

    assert restored == specification
    assert json.loads(payload) == specification.to_record()


@pytest.mark.parametrize(
    "legacy_record",
    [
        {
            "schema_version": "1.0",
            "agent_type": "one_prompt",
            "template": "one_prompt",
            "purpose": "Summarize support requests",
            "audience": "",
            "inputs": [],
            "instructions": "Return a concise summary.",
            "constraints": [],
            "knowledge_sources": [],
            "tools": [],
            "expected_result": "A short summary",
            "parameters": {},
            "status": "ready",
            "validation": {
                "status": "ready",
                "missing_fields": [],
                "issues": [],
            },
        },
        {
            "schema_version": "1.0",
            "agent_type": "rag",
            "template": "rag",
            "purpose": "Answer from documents",
            "audience": "",
            "inputs": [],
            "instructions": "Search before answering.",
            "constraints": [],
            "knowledge_sources": [
                {
                    "source_id": "file-1",
                    "title": "guide.pdf",
                    "kind": "uploaded_file",
                    "reference": "file-1",
                }
            ],
            "tools": [
                {
                    "tool_id": "knowledge_search",
                    "title": "Knowledge search",
                    "description": "Searches the connected AI Studio vector index.",
                    "parameters": {
                        "index_id": "vs-123",
                        "index_name": "docs",
                    },
                }
            ],
            "expected_result": "A grounded answer",
            "parameters": {
                "index_id": "vs-123",
                "index_name": "docs",
                "ttl_days": 1,
            },
            "status": "ready",
            "validation": {
                "status": "ready",
                "missing_fields": [],
                "issues": [],
            },
        },
    ],
)
def test_pre_code_interpreter_schema_1_0_records_remain_byte_compatible(
    legacy_record: dict,
) -> None:
    payload = json.dumps(
        legacy_record,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    restored = loads_agent_specification(payload)

    assert dumps_agent_specification(restored) == payload


def test_record_loader_requires_json_object_root() -> None:
    with pytest.raises(InvalidSpecificationRootError, match="root must be an object"):
        load_agent_specification([])


@pytest.mark.parametrize(
    "payload, message",
    [
        ('{"schema_version": "1.0", "schema_version": "1.0"}', "duplicate key"),
        ('{"value": NaN}', "non-finite number"),
    ],
)
def test_json_loader_rejects_non_strict_json(payload: str, message: str) -> None:
    with pytest.raises(InvalidSpecificationJSONError, match=message):
        loads_agent_specification(payload)


def test_json_loader_reports_syntax_location() -> None:
    with pytest.raises(InvalidSpecificationJSONError) as error:
        loads_agent_specification('{"schema_version":')

    assert error.value.lineno == 1
    assert error.value.colno == 19


def test_json_loader_rejects_non_utf8_bytes() -> None:
    with pytest.raises(InvalidSpecificationJSONError, match="UTF-8"):
        loads_agent_specification(b"\xff")
