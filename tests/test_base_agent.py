import asyncio
from pathlib import Path
from typing import Any, cast

from agents import RunConfig
from openai import OpenAI

from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.application.settings import ModelConfig
from ai_studio_agent_builder.builder.agents.base_agent import CustomAgent
from ai_studio_agent_builder.builder.context import RequestContext


class EmptyStreamingResult:
    async def stream_events(self):
        if False:
            yield None


def test_custom_agent_passes_configured_max_turns_to_runner(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    def fake_run_streamed(**kwargs):
        captured.update(kwargs)
        return EmptyStreamingResult()

    monkeypatch.setattr(
        "ai_studio_agent_builder.builder.agents.base_agent.Runner.run_streamed",
        fake_run_streamed,
    )
    agent = CustomAgent(
        ModelConfig(
            model_name="test-model",
            temperature=0.0,
            max_output_tokens=100,
            base_url="https://example.test/v1",
            sessions_db_path=tmp_path / "session.db",
            max_turns=20,
        ),
        name="Test Agent",
        instruction="Test instructions",
        session_factory=lambda user_id, path: cast(Any, object()),
    )
    context = RequestContext(
        user_id="user-1",
        request_id="request-1",
        user_files_dir=tmp_path,
        client=cast(OpenAI, object()),
        state=ConversationState(),
        folder_id="folder-1",
    )

    async def collect_events() -> None:
        async for _event in agent.respond(
            "Hello", context, run_config=cast(RunConfig, object())
        ):
            pass

    asyncio.run(collect_events())

    assert captured["max_turns"] == 20
