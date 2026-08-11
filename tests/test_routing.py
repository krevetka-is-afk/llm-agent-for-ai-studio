import pytest

from ai_studio_agent_builder.domain.routing import (
    ConversationOptions,
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
