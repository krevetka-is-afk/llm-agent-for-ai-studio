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
- `example.py` — минимальный запуск через Yandex AI Studio Responses API;
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

API-ключ и folder ID намеренно не включены в архив. Для RAG существующий
Vector Store должен быть доступен в выбранном каталоге и не должен быть удалён
по TTL.
"""

DEVELOPER_ENV_EXAMPLE = """YC_AI_STUDIO_API_KEY=replace_with_api_key
YC_AI_STUDIO_FOLDER_ID=replace_with_folder_id
"""

DEVELOPER_EXAMPLE = """import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()
api_key = os.environ["YC_AI_STUDIO_API_KEY"]
folder_id = os.environ["YC_AI_STUDIO_FOLDER_ID"]
config = json.loads(
    Path("responses-agent-config.json").read_text(encoding="utf-8")
)

client = OpenAI(
    api_key=api_key,
    project=folder_id,
    base_url="https://ai.api.cloud.yandex.net/v1",
    default_headers={"Authorization": f"Api-Key {api_key}"},
)

request = {
    "model": f"gpt://{folder_id}/{config['model_name']}",
    "instructions": config["instructions"],
    "input": input("Введите запрос агенту: ").strip(),
    "temperature": config["temperature"],
    "max_output_tokens": config["max_output_tokens"],
}
if config["tools"]:
    request["tools"] = config["tools"]

response = client.responses.create(**request)
print(response.output_text)
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
