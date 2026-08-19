from ai_studio_agent_builder.builder.agents.coordinator_agent import (
    COORDINATOR_AGENT_INSTRUCTIONS,
)
from ai_studio_agent_builder.builder.agents.one_prompt_agent import (
    ONE_PROMPT_AGENT_INSTRUCTIONS,
)
from ai_studio_agent_builder.builder.agents.rag_agent import RAG_AGENT_INSTRUCTIONS


def _normalized(prompt: str) -> str:
    return " ".join(prompt.casefold().split())


def test_agent_prompts_do_not_contain_known_paste_or_markdown_artifacts() -> None:
    prompts = (
        COORDINATOR_AGENT_INSTRUCTIONS,
        ONE_PROMPT_AGENT_INSTRUCTIONS,
        RAG_AGENT_INSTRUCTIONS,
    )

    for prompt in prompts:
        assert "Обновлённый системный промпт" not in prompt
        assert "confirmation**" not in prompt


def test_agent_prompts_apply_non_overridable_content_policy() -> None:
    prompts = (
        COORDINATOR_AGENT_INSTRUCTIONS,
        ONE_PROMPT_AGENT_INSTRUCTIONS,
        RAG_AGENT_INSTRUCTIONS,
    )

    for prompt in prompts:
        normalized = _normalized(prompt)
        assert "content policy (highest priority" in normalized
        assert "respond in russian by default" in normalized
        assert "explicitly requests it for an allowed, in-scope task" in normalized
        assert "policy refusals in russian" in normalized
        assert "never discuss politics" in normalized
        assert "conflict between russia and ukraine" in normalized
        assert "euphemisms" in normalized
        assert "uploaded files" in normalized
        assert "untrusted data" in normalized
        assert "builder scope" in normalized


def test_agent_prompts_distinguish_web_search_from_vector_rag() -> None:
    coordinator = _normalized(COORDINATOR_AGENT_INSTRUCTIONS)
    one_prompt = _normalized(ONE_PROMPT_AGENT_INSTRUCTIONS)

    assert "веб-поиск сам по себе не является rag" in coordinator
    assert "явный отказ пользователя от rag" in coordinator
    assert "web search does not require a vector index" in one_prompt
    assert "do not request knowledge_sources or index_id" in one_prompt
    assert "web_search=true" in one_prompt
    assert "web_search=false" in one_prompt
    assert "keep knowledge_sources empty" in one_prompt


def test_agent_prompts_distinguish_code_execution_from_vector_knowledge() -> None:
    coordinator = _normalized(COORDINATOR_AGENT_INSTRUCTIONS)
    one_prompt = _normalized(ONE_PROMPT_AGENT_INSTRUCTIONS)
    rag = _normalized(RAG_AGENT_INSTRUCTIONS)

    assert "анализ csv/xlsx" in coordinator
    assert "сам факт приложения файла не означает rag" in coordinator
    assert "поиск по документам и вычисления" in coordinator
    assert "code_interpreter=true" in one_prompt
    assert "code_interpreter=false" in one_prompt
    assert "do not request or invent file_ids or container_id" in one_prompt
    assert "code_interpreter=true" in rag
    assert "code_interpreter=false" in rag
    assert "не становятся файлами code interpreter автоматически" in rag
