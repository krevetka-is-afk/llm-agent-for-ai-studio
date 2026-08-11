import logging
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from agents import Agent, RunConfig, Runner
from agents.memory import SQLiteSession
from agents.tool import Tool

from ai_studio_agent_builder.builder.context import RequestContext
from ai_studio_agent_builder.application.settings import ModelConfig


logger = logging.getLogger(__name__)
SessionFactory = Callable[[str, Path], SQLiteSession]


class CustomAgent:
    def __init__(
        self,
        model_config: ModelConfig,
        name: str,
        instruction: str,
        session_factory: SessionFactory,
        tools: list[Tool] | None = None,
    ):
        self.session_db_path = model_config.sessions_db_path
        self.model_config = model_config
        self.name = name
        self.instruction = instruction
        self._session_factory = session_factory
        self.tools = tools or []

    async def respond(
        self, message: str, context: RequestContext, run_config: RunConfig
    ) -> AsyncIterator[Any]:
        if not message.strip():
            return

        request_logger = logging.LoggerAdapter(
            logger,
            {"user_id": context.user_id, "request_id": context.request_id},
        )
        request_logger.info(
            "Invoking %s with %s chars of user input", self.name, len(message)
        )
        session = self._session_factory(context.user_id, self.session_db_path)

        request_logger.info("Invoking %s model", self.name)
        agent = Agent(
            model=f"gpt://{context.folder_id}/{self.model_config.model_name}",
            name=self.name,
            instructions=self.instruction,
            tools=self.tools,
        )
        result = Runner.run_streamed(
            starting_agent=agent,
            input=message,
            context=context,
            max_turns=self.model_config.max_turns,
            run_config=run_config,
            session=session,
        )

        async for event in result.stream_events():
            yield event
