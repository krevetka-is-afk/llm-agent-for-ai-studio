from custom_agents.coordinator_agent import COORDINATOR_AGENT_INSTRUCTIONS
from custom_agents.one_prompt_agent import ONE_PROMPT_AGENT_INSTRUCTIONS


def test_agent_prompts_do_not_contain_known_paste_or_markdown_artifacts() -> None:
    prompts = (COORDINATOR_AGENT_INSTRUCTIONS, ONE_PROMPT_AGENT_INSTRUCTIONS)

    for prompt in prompts:
        assert "Обновлённый системный промпт" not in prompt
        assert "confirmation**" not in prompt
