from __future__ import annotations

import csv
import io
import os
import time
import warnings
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from openai import OpenAI
from openai.types.responses.tool_param import CodeInterpreter


pytestmark = [
    pytest.mark.yandex_ai_studio_e2e,
    pytest.mark.skipif(
        os.getenv("RUN_YANDEX_AI_STUDIO_E2E") != "1",
        reason="Set RUN_YANDEX_AI_STUDIO_E2E=1 to run credentialed E2E tests",
    ),
]

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "code_interpreter"
TERMINAL_RESPONSE_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "incomplete"}
)


def test_yandex_code_interpreter_accepts_files_and_returns_artifact() -> None:
    client, folder_id, model_name = _client_from_environment()
    input_file_ids: list[str] = []
    output_file_ids: set[str] = set()
    container_ids: set[str] = set()
    response_id: str | None = None
    response: Any | None = None

    try:
        for filename in ("context.txt", "numbers.csv"):
            with (FIXTURE_DIR / filename).open("rb") as source:
                uploaded = client.files.create(file=source, purpose="user_data")
            input_file_ids.append(uploaded.id)

        tools: list[CodeInterpreter] = [
            {
                "type": "code_interpreter",
                "container": {
                    "type": "auto",
                    "file_ids": input_file_ids,
                    "memory_limit": "1g",
                    "network_policy": {"type": "disabled"},
                },
            }
        ]
        stream = client.responses.create(
            model=f"gpt://{folder_id}/{model_name}",
            instructions=(
                "Use Code Interpreter for calculations and file generation. "
                "Do not calculate mentally."
            ),
            input=(
                "Read both attached files. Sum the CSV value column, apply the "
                "multiplier from the text file, create result.csv with columns "
                "metric,value and rows sum, multiplier, result, then answer with "
                "CODE_INTERPRETER_CONTRACT_OK and cite result.csv."
            ),
            tool_choice="required",
            temperature=0.0,
            tools=tools,
            stream=True,
        )
        for event in stream:
            event_response = _value(event, "response")
            candidate = _value(event_response, "id")
            if isinstance(candidate, str):
                response_id = candidate

        assert response_id is not None, "stream did not expose a response ID"
        response = _wait_for_terminal_response(client, response_id)
        _collect_remote_references(response, output_file_ids, container_ids)

        assert _value(response, "status") == "completed"
        assert "CODE_INTERPRETER_CONTRACT_OK" in (_value(response, "output_text") or "")
        assert _has_completed_code_interpreter_call(response)

        artifacts = _container_file_artifacts(response)
        result_file_ids = [
            file_id for file_id, filename in artifacts if filename == "result.csv"
        ]
        assert len(result_file_ids) == 1
        payload = client.files.content(result_file_ids[0]).read()
        assert len(payload) <= 1024 * 1024
        rows = {
            row["metric"]: float(row["value"])
            for row in csv.DictReader(io.StringIO(payload.decode("utf-8")))
        }
        assert rows == {"sum": 50.0, "multiplier": 2.0, "result": 100.0}
    finally:
        if response is None and response_id is not None:
            try:
                response = client.responses.retrieve(response_id)
                _collect_remote_references(
                    response,
                    output_file_ids,
                    container_ids,
                )
            except Exception:
                _warn_cleanup("response lookup")
        _cleanup_remote_resources(
            client,
            input_file_ids=input_file_ids,
            output_file_ids=output_file_ids,
            container_ids=container_ids,
            response_id=response_id,
        )


def _client_from_environment() -> tuple[OpenAI, str, str]:
    api_key = os.getenv("YC_AI_STUDIO_API_KEY")
    folder_id = os.getenv("YC_AI_STUDIO_FOLDER_ID")
    if not api_key or not folder_id:
        pytest.fail(
            "RUN_YANDEX_AI_STUDIO_E2E=1 requires YC_AI_STUDIO_API_KEY and "
            "YC_AI_STUDIO_FOLDER_ID"
        )
    client = OpenAI(
        api_key=api_key,
        project=folder_id,
        base_url=os.getenv(
            "YC_AI_STUDIO_BASE_URL",
            "https://ai.api.cloud.yandex.net/v1",
        ),
        timeout=float(os.getenv("YC_AI_STUDIO_REQUEST_TIMEOUT_SECONDS", "90")),
        default_headers={"Authorization": f"Api-Key {api_key}"},
    )
    return client, folder_id, os.getenv("YC_AI_STUDIO_MODEL", "gpt-oss-120b")


def _wait_for_terminal_response(client: OpenAI, response_id: str) -> Any:
    deadline = time.monotonic() + float(
        os.getenv("YC_AI_STUDIO_E2E_TIMEOUT_SECONDS", "420")
    )
    while True:
        response = client.responses.retrieve(response_id)
        if _value(response, "status") in TERMINAL_RESPONSE_STATUSES:
            return response
        if time.monotonic() >= deadline:
            raise TimeoutError("Code Interpreter response polling timed out")
        time.sleep(3)


def _has_completed_code_interpreter_call(response: Any) -> bool:
    return any(
        _value(item, "type") == "code_interpreter_call"
        and _value(item, "status") == "completed"
        for item in _response_output(response)
    )


def _container_file_artifacts(response: Any) -> list[tuple[str, str]]:
    artifacts: list[tuple[str, str]] = []
    for annotation in _response_annotations(response):
        if _value(annotation, "type") != "container_file_citation":
            continue
        file_id = _value(annotation, "file_id")
        filename = _value(annotation, "filename")
        if isinstance(file_id, str) and isinstance(filename, str):
            artifacts.append((file_id, filename))
    return artifacts


def _collect_remote_references(
    response: Any,
    output_file_ids: set[str],
    container_ids: set[str],
) -> None:
    for item in _response_output(response):
        if _value(item, "type") == "code_interpreter_call":
            container_id = _value(item, "container_id")
            if isinstance(container_id, str):
                container_ids.add(container_id)
    for annotation in _response_annotations(response):
        file_id = _value(annotation, "file_id")
        if isinstance(file_id, str):
            output_file_ids.add(file_id)
        container_id = _value(annotation, "container_id")
        if isinstance(container_id, str):
            container_ids.add(container_id)


def _response_annotations(response: Any) -> list[Any]:
    annotations: list[Any] = []
    for item in _response_output(response):
        content = _value(item, "content")
        if not _is_sequence(content):
            continue
        for content_item in content:
            item_annotations = _value(content_item, "annotations")
            if _is_sequence(item_annotations):
                annotations.extend(item_annotations)
    return annotations


def _response_output(response: Any) -> Sequence[Any]:
    output = _value(response, "output")
    return output if _is_sequence(output) else ()


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        str | bytes | bytearray,
    )


def _value(source: Any, name: str) -> Any:
    if isinstance(source, Mapping):
        return source.get(name)
    return getattr(source, name, None)


def _cleanup_remote_resources(
    client: OpenAI,
    *,
    input_file_ids: Sequence[str],
    output_file_ids: set[str],
    container_ids: set[str],
    response_id: str | None,
) -> None:
    if os.getenv("YC_AI_STUDIO_E2E_KEEP_REMOTE") == "1":
        return
    for file_id in sorted(output_file_ids | set(input_file_ids)):
        try:
            client.files.delete(file_id)
        except Exception:
            _warn_cleanup("file")
    for container_id in sorted(container_ids):
        try:
            client.containers.delete(container_id)
        except Exception:
            _warn_cleanup("container")
    if response_id is not None:
        try:
            client.responses.delete(response_id)
        except Exception:
            _warn_cleanup("response")


def _warn_cleanup(resource: str) -> None:
    warnings.warn(
        f"Credentialed Code Interpreter E2E could not delete remote {resource}",
        RuntimeWarning,
        stacklevel=2,
    )
