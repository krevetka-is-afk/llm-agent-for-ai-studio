# Архитектура MVP

## Основной поток

1. Web UI или Telegram adapter формирует `InteractionRequest` с уникальным
   `request_id`.
2. `AIInteractionService` создаёт clients Yandex AI Studio на границе сервиса.
3. Агент получает `RequestContext` без API-ключа: только client, folder ID,
   директорию файлов, разрешённые file IDs и рабочую копию состояния.
4. Coordinator при необходимости делегирует запрос RAG или one-prompt агенту.
5. `ResultAssembler` собирает текст и типизированные результаты tool calls.
6. Новое состояние диалога коммитится только после успешной сборки результата.

## Границы модулей

- `credentials.py` — модели credentials и фабрики sync/async OpenAI clients.
- `conversation_state.py` — enum и mutable state маршрутизации.
- `user_store.py` — экспериментальное in-memory хранилище Telegram-пользователей.
- `request_context.py` — least-privilege context, доступный агентам и tools.
- `context.py` — временный compatibility shim для стабильности старых импортов.
- `ai_interaction_service.py` — application orchestration, uploads, delegation и
  transaction boundary.
- `result_assembly.py` — authoritative tool results и их текстовая проекция.

Streamlit entrypoint остаётся `src/ui/app.py`, но детали разделены:

- `connection.py` — подключение и lifecycle API-ключа;
- `uploads.py` — чистая валидация upload metadata;
- `attachments.py` — безопасное отображение и скачивание файлов;
- `result_view.py` — карточки типизированных результатов;
- `chat_flow.py` — history, submission и interaction flow.

## Осознанно отложено

- полный перенос flat modules в единый installable package;
- постоянное хранилище Telegram accounts и миграции;
- интеграция OAuth Gateway в основной credential flow;
- multi-replica coordination и distributed locks.

Эти изменения не нужны для текущего MVP и расширили бы blast radius перед
релизом.
