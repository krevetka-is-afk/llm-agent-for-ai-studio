# llm-agent-for-ai-studio
Ассистент, который поможет пользователям собирать агентов из кубиков AI studio.

## Установка

### Пререквизит

`uv` & `≥python3.14`

### Клонируем репозиторий

```bash
git clone https://github.com/krevetka-is-afk/llm-agent-for-ai-studio.git
cd llm-agent-for-ai-studio
```

### Устанавливаем зависимости

```bash
uv sync --frozen
```

#### Для участия в разработке необходимо дополнительно

```bash
uv run pre-commit install
```

##### Перед коммитом

```bash
uv run pre-commit run --all-files
```

## Запуск проекта

>[!warning]
>Перед запуском добавьте переменные окружения (минимально необходимые обозначены в [.env.example](.env.example))

```bash
cd src/
uv run --env-file ../.env.example main.py [--file-dir]
```

## Запуск в docker

>[!warning]
>Перед запуском добавьте переменные окружения (минимально необходимые обозначены в [.env.example](.env.example))

```bash
docker build -t my-rag-agent .
docker run -d --name my-rag-agent --restart unless-stopped my-rag-agent
```
