import pytest

from ai_studio_agent_builder.domain.routing import (
    ConversationOptions,
    RoutingReason,
    resolve_explicit_route,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("3. веб-поиск", ConversationOptions.ONE_PROMPT),
        (
            "Думаю, пока без файлов. Давай двигаться дальше",
            ConversationOptions.ONE_PROMPT,
        ),
        (
            "Сформируем system-prompt и спецификацию агента без RAG",
            ConversationOptions.ONE_PROMPT,
        ),
        ("Мне не нужен векторный поиск!", ConversationOptions.ONE_PROMPT),
        ("Векторный поиск мне не нужен", ConversationOptions.ONE_PROMPT),
        ("Я не хочу использовать RAG", ConversationOptions.ONE_PROMPT),
        ("RAG мне точно не нужен", ConversationOptions.ONE_PROMPT),
        ("Создай индекс из файлов", ConversationOptions.RAG),
        ("Хочу RAG и веб-поиск", ConversationOptions.RAG),
        ("Включи Code Interpreter", ConversationOptions.ONE_PROMPT),
        ("Мне нужен интерпретатор кода", ConversationOptions.ONE_PROMPT),
        ("Проанализируй приложенный CSV", ConversationOptions.ONE_PROMPT),
        ("Обработай эту таблицу XLSX", ConversationOptions.ONE_PROMPT),
        ("Сделай расчёт по файлу", ConversationOptions.ONE_PROMPT),
        ("Построй график по данным из файла", ConversationOptions.ONE_PROMPT),
        ("Analyze this CSV with Python", ConversationOptions.ONE_PROMPT),
        ("Создай RAG по PDF", ConversationOptions.RAG),
        ("Ищи по отчётам и построй график", ConversationOptions.RAG),
        ("Search uploaded documents and analyze the CSV", ConversationOptions.RAG),
        ("Давай сделаем чат-бота", None),
    ],
)
def test_explicit_route_resolver_covers_incident_phrases(
    message: str, expected: ConversationOptions | None
) -> None:
    decision = resolve_explicit_route(message)

    assert (decision.target if decision else None) is expected


def test_rejecting_web_search_does_not_imply_a_rag_route() -> None:
    assert resolve_explicit_route("Мне не нужен веб-поиск") is None


def test_rejecting_code_interpreter_does_not_create_a_new_route() -> None:
    assert resolve_explicit_route("Мне не нужен интерпретатор кода") is None


def test_code_interpreter_route_has_a_distinct_reason() -> None:
    decision = resolve_explicit_route("Построй график по приложенному CSV")

    assert decision is not None
    assert decision.target is ConversationOptions.ONE_PROMPT
    assert decision.reason is RoutingReason.CODE_INTERPRETER_WITHOUT_VECTOR_KNOWLEDGE
