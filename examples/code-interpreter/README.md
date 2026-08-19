# Code Interpreter: безопасный integration flow

Каталог показывает два стабильных слоя экспорта:

- `agent-specification.json` — переносимая capability без provider state;
- `responses-agent-config.json` — базовый auto-container без `file_ids`.

Канонический исполняемый `example.py` генерируется в ZIP-пакете готовой
карточки агента. Он связан с выбранной спецификацией и поэтому не дублируется
здесь как независимая копия. Скачать пакет можно через «Скачать пакет для
разработчика (.zip)» в Streamlit UI.

## Запуск generated bundle

```bash
python3 -m venv .venv
.venv/bin/python -m pip install openai python-dotenv
cp .env.example .env
.venv/bin/python example.py \
  --prompt "Посчитай сумму столбца value и создай result.csv" \
  --file numbers.csv
```

Порядок выполнения:

1. проверить до 5 локальных файлов и лимиты 10 MiB на файл/25 MiB суммарно;
2. загрузить каждый input с `purpose=user_data`;
3. добавить полученные IDs только в копию Code Interpreter tool текущего
   request;
4. выполнить Responses API call;
5. найти `container_file_citation` и потоково скачать до 10 outputs с лимитами;
6. удалить известные input/output files, auto-container и response в `finally`.

`agent-specification.json` и `responses-agent-config.json` не изменяются во
время запуска. Не коммитьте `.env`, пользовательские inputs, каталог
`generated/` или provider IDs.

## Безопасные defaults и эксплуатация

- auto-container;
- 1 GiB памяти;
- сеть выключена;
- API-key scope `yc.ai.foundationModels.execute`;
- роли сервисного аккаунта `ai.assistants.editor` и `ai.languageModels.user`;
- provider TTL auto-container — 20 минут после последней активности, но явный
  cleanup обязателен;
- контракт проверен на `gpt-oss-120b`; другую модель нужно подтвердить
  credentialed E2E;
- стоимость и квоты сверяются с актуальными условиями Yandex AI Studio перед
  production deployment.

Официальные источники: [пример использования Code Interpreter](https://aistudio.yandex.ru/docs/ru/ai-studio/operations/agents/use-code-interpreter.html)
и [описание инструмента](https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/agents/tools/code-interpreter.html).
