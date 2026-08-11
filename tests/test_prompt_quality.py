from ai_studio_agent_builder.builder.agents.coordinator_agent import (
    COORDINATOR_AGENT_INSTRUCTIONS,
)
from ai_studio_agent_builder.builder.agents.one_prompt_agent import (
    ONE_PROMPT_AGENT_INSTRUCTIONS,
)


def test_agent_prompts_do_not_contain_known_paste_or_markdown_artifacts() -> None:
    prompts = (COORDINATOR_AGENT_INSTRUCTIONS, ONE_PROMPT_AGENT_INSTRUCTIONS)

    for prompt in prompts:
        assert "Обновлённый системный промпт" not in prompt
        assert "confirmation**" not in prompt


def test_agent_prompts_distinguish_web_search_from_vector_rag() -> None:
    coordinator = COORDINATOR_AGENT_INSTRUCTIONS.casefold()
    one_prompt = ONE_PROMPT_AGENT_INSTRUCTIONS.casefold()

    assert "веб-поиск сам по себе не является rag" in coordinator
    assert "явный отказ пользователя от rag" in coordinator
    assert "web search does not require a vector index" in one_prompt
    assert "do not request knowledge_sources or index_id" in one_prompt
    assert "web_search=true" in one_prompt
    assert "web_search=false" in one_prompt
    assert "keep knowledge_sources empty" in one_prompt
