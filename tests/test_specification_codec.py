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
