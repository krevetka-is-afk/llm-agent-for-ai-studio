"""Build the downloadable handoff archive for a generated agent."""

import io
import json
import zipfile
from collections.abc import Mapping
from typing import Any


DEVELOPER_README = """# Generated agent integration package

Этот архив предназначен для разработчика, который подключит проверенного агента
к сайту, боту или внутреннему приложению.

## Содержимое

- `agent-specification.json` — назначение и требования к агенту;
- `responses-agent-config.json` — конфигурация, использованная при тестировании;
- `example.py` — безопасный запуск через Yandex AI Studio Responses API;
- `.env.example` — имена необходимых переменных окружения без секретов.

## Запуск примера

Установите Python 3.11 или новее. Затем выполните команды для своей системы.

### Bash (Linux, macOS, Git Bash)

```bash
python3 -m venv .venv
.venv/bin/python -m pip install openai python-dotenv
cp .env.example .env
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install openai python-dotenv
Copy-Item .env.example .env
```

### Windows Command Prompt (CMD)

```bat
py -3 -m venv .venv
.venv\\Scripts\\python.exe -m pip install openai python-dotenv
copy /Y .env.example .env
```

Откройте созданный `.env` в текстовом редакторе и замените оба значения:

```dotenv
YC_AI_STUDIO_API_KEY=replace_with_api_key
YC_AI_STUDIO_FOLDER_ID=replace_with_folder_id
```

После сохранения `.env` запустите пример.

В Bash:

```bash
.venv/bin/python example.py
```

В Windows PowerShell:

```powershell
.\\.venv\\Scripts\\python.exe example.py
```

В Windows CMD:

```bat
.venv\\Scripts\\python.exe example.py
```

Если агент использует Code Interpreter, передайте входные файлы явно для
конкретного запуска:

```bash
.venv/bin/python example.py --file data.csv --file instructions.txt
```

Пример проверяет локальные лимиты, загружает файлы с `purpose=user_data`,
добавляет их ID только в копию request config, скачивает созданные артефакты в
`generated/` и удаляет известные remote files, auto-container и response в
`finally`. `responses-agent-config.json` при этом не изменяется. Auto-container
создаётся с 1 GiB памяти, выключенной сетью и provider TTL 20 минут; явный
cleanup всё равно обязателен.

API-ключ и folder ID намеренно не включены в архив. Для RAG существующий
Vector Store должен быть доступен в выбранном каталоге и не должен быть удалён
по TTL. ZIP также никогда не включает пользовательские файлы, временные
Code Interpreter file/container IDs или созданные артефакты.
"""

DEVELOPER_ENV_EXAMPLE = """YC_AI_STUDIO_API_KEY=replace_with_api_key
YC_AI_STUDIO_FOLDER_ID=replace_with_folder_id
"""

DEVELOPER_EXAMPLE = """import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


MAX_INPUT_FILES = 5
MAX_INPUT_FILE_BYTES = 10 * 1024 * 1024
MAX_INPUT_TOTAL_BYTES = 25 * 1024 * 1024
MAX_OUTPUT_FILES = 10
MAX_OUTPUT_FILE_BYTES = 10 * 1024 * 1024
MAX_OUTPUT_TOTAL_BYTES = 25 * 1024 * 1024
STREAM_CHUNK_BYTES = 64 * 1024


def main() -> None:
    arguments = _parse_arguments()
    load_dotenv()
    api_key = os.environ["YC_AI_STUDIO_API_KEY"]
    folder_id = os.environ["YC_AI_STUDIO_FOLDER_ID"]
    config = json.loads(
        Path("responses-agent-config.json").read_text(encoding="utf-8")
    )
    input_paths = _validate_input_paths(arguments.file)
    tools = copy.deepcopy(config["tools"])
    if input_paths and not _has_code_interpreter(tools):
        raise SystemExit("--file requires a Code Interpreter tool")

    client = OpenAI(
        api_key=api_key,
        project=folder_id,
        base_url="https://ai.api.cloud.yandex.net/v1",
        default_headers={"Authorization": f"Api-Key {api_key}"},
    )
    input_file_ids: list[str] = []
    output_file_ids: set[str] = set()
    container_ids: set[str] = set()
    response_id: str | None = None

    try:
        _upload_inputs(client, input_paths, input_file_ids)
        request_tools = _bind_code_interpreter_files(tools, input_file_ids)
        prompt = arguments.prompt or input("Введите запрос агенту: ").strip()
        if not prompt:
            raise SystemExit("Запрос агенту не должен быть пустым")
        request: dict[str, Any] = {
            "model": f"gpt://{folder_id}/{config['model_name']}",
            "instructions": config["instructions"],
            "input": prompt,
            "temperature": config["temperature"],
            "max_output_tokens": config["max_output_tokens"],
        }
        if request_tools:
            request["tools"] = request_tools

        response = client.responses.create(**request)
        candidate_response_id = _value(response, "id")
        if isinstance(candidate_response_id, str):
            response_id = candidate_response_id
        artifacts, container_ids = _collect_artifacts(response)
        output_file_ids.update(file_id for file_id, _ in artifacts)
        output_text = _value(response, "output_text")
        if isinstance(output_text, str):
            print(output_text)
        for generated_path in _download_outputs(client, artifacts):
            print(f"Создан файл: {generated_path}")
    finally:
        _cleanup_remote_resources(
            client,
            input_file_ids=input_file_ids,
            output_file_ids=output_file_ids,
            container_ids=container_ids,
            response_id=response_id,
        )


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the generated agent")
    parser.add_argument("--prompt", help="Prompt without an interactive input")
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        type=Path,
        help="Input file for Code Interpreter; repeat for multiple files",
    )
    return parser.parse_args()


def _validate_input_paths(paths: list[Path]) -> list[Path]:
    if len(paths) > MAX_INPUT_FILES:
        raise SystemExit(f"At most {MAX_INPUT_FILES} input files are allowed")
    total_bytes = 0
    validated: list[Path] = []
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise SystemExit(f"Input must be a regular non-symlink file: {path}")
        size = path.stat().st_size
        if size > MAX_INPUT_FILE_BYTES:
            raise SystemExit(f"Input file exceeds 10 MiB: {path.name}")
        total_bytes += size
        if total_bytes > MAX_INPUT_TOTAL_BYTES:
            raise SystemExit("Input files exceed the 25 MiB total limit")
        validated.append(path)
    return validated


def _has_code_interpreter(tools: list[dict[str, Any]]) -> bool:
    return any(tool.get("type") == "code_interpreter" for tool in tools)


def _upload_inputs(client: Any, paths: list[Path], uploaded_ids: list[str]) -> None:
    for path in paths:
        with path.open("rb") as source:
            uploaded = client.files.create(file=source, purpose="user_data")
        file_id = _value(uploaded, "id")
        if not isinstance(file_id, str) or not file_id:
            raise RuntimeError("Files API did not return an input file ID")
        uploaded_ids.append(file_id)


def _bind_code_interpreter_files(
    tools: list[dict[str, Any]],
    file_ids: list[str],
) -> list[dict[str, Any]]:
    if not file_ids:
        return tools
    code_tools = [tool for tool in tools if tool.get("type") == "code_interpreter"]
    if len(code_tools) != 1:
        raise RuntimeError("Expected exactly one Code Interpreter tool")
    container = code_tools[0].get("container")
    if not isinstance(container, dict) or container.get("type") != "auto":
        raise RuntimeError("Only the auto Code Interpreter container is supported")
    code_tools[0]["container"] = {**container, "file_ids": list(file_ids)}
    return tools


def _collect_artifacts(response: Any) -> tuple[list[tuple[str, str]], set[str]]:
    artifacts: list[tuple[str, str]] = []
    seen_file_ids: set[str] = set()
    container_ids: set[str] = set()
    output = _value(response, "output")
    for item in output if isinstance(output, list | tuple) else ():
        if _value(item, "type") == "code_interpreter_call":
            container_id = _value(item, "container_id")
            if isinstance(container_id, str):
                container_ids.add(container_id)
        content = _value(item, "content")
        for content_item in content if isinstance(content, list | tuple) else ():
            annotations = _value(content_item, "annotations")
            for annotation in (
                annotations if isinstance(annotations, list | tuple) else ()
            ):
                if _value(annotation, "type") != "container_file_citation":
                    continue
                file_id = _value(annotation, "file_id")
                filename = _value(annotation, "filename")
                container_id = _value(annotation, "container_id")
                if isinstance(container_id, str):
                    container_ids.add(container_id)
                if (
                    isinstance(file_id, str)
                    and isinstance(filename, str)
                    and file_id not in seen_file_ids
                ):
                    seen_file_ids.add(file_id)
                    artifacts.append((file_id, filename))
    return artifacts, container_ids


def _download_outputs(client: Any, artifacts: list[tuple[str, str]]) -> list[Path]:
    output_dir = Path("generated")
    generated_paths: list[Path] = []
    total_bytes = 0
    for file_id, filename in artifacts[:MAX_OUTPUT_FILES]:
        target = _unique_output_path(output_dir, filename)
        partial = target.with_name(f".{target.name}.partial")
        written = 0
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            with client.files.with_streaming_response.content(file_id) as response:
                with partial.open("xb") as destination:
                    for chunk in response.iter_bytes(chunk_size=STREAM_CHUNK_BYTES):
                        if not isinstance(chunk, bytes):
                            raise TypeError("Files API returned a non-bytes chunk")
                        written += len(chunk)
                        if written > MAX_OUTPUT_FILE_BYTES:
                            raise RuntimeError("Generated file exceeds 10 MiB")
                        if total_bytes + written > MAX_OUTPUT_TOTAL_BYTES:
                            raise RuntimeError("Generated files exceed 25 MiB total")
                        destination.write(chunk)
            partial.replace(target)
        except Exception:
            partial.unlink(missing_ok=True)
            raise
        total_bytes += written
        generated_paths.append(target)
    if len(artifacts) > MAX_OUTPUT_FILES:
        print(f"Пропущено файлов сверх лимита: {len(artifacts) - MAX_OUTPUT_FILES}")
    return generated_paths


def _unique_output_path(output_dir: Path, filename: str) -> Path:
    safe_name = Path(filename.replace("\\\\", "/")).name or "generated-file"
    candidate = output_dir / safe_name
    counter = 1
    while candidate.exists() or candidate.with_name(f".{candidate.name}.partial").exists():
        candidate = output_dir / f"{Path(safe_name).stem}-{counter}{Path(safe_name).suffix}"
        counter += 1
    return candidate


def _cleanup_remote_resources(
    client: Any,
    *,
    input_file_ids: list[str],
    output_file_ids: set[str],
    container_ids: set[str],
    response_id: str | None,
) -> None:
    for file_id in sorted(set(input_file_ids) | output_file_ids):
        _delete_quietly("file", client.files.delete, file_id)
    for container_id in sorted(container_ids):
        _delete_quietly("container", client.containers.delete, container_id)
    if response_id is not None:
        _delete_quietly("response", client.responses.delete, response_id)


def _delete_quietly(resource: str, delete: Any, resource_id: str) -> None:
    try:
        delete(resource_id)
    except Exception:
        print(f"Не удалось удалить remote {resource}; проверьте provider TTL")


def _value(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


if __name__ == "__main__":
    main()
"""


def build_developer_bundle(
    specification: Mapping[str, Any],
    runtime_json: str,
) -> bytes:
    specification_json = json.dumps(
        dict(specification),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr("agent-specification.json", specification_json)
        archive.writestr("responses-agent-config.json", runtime_json)
        archive.writestr("example.py", DEVELOPER_EXAMPLE)
        archive.writestr(".env.example", DEVELOPER_ENV_EXAMPLE)
        archive.writestr("README.md", DEVELOPER_README)
    return buffer.getvalue()
