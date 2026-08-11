import logging

from agents import Agent, RunConfig, Runner
from agents.memory import SQLiteSession
from agents.tool import Tool

from ai_studio_agent_builder.builder.context import RequestContext
from ai_studio_agent_builder.config import ModelConfig
from ai_studio_agent_builder.infrastructure.persistence.agent_sessions import (
    get_session,
)
from ai_studio_agent_builder.infrastructure.observability.logging import bind_logger

from typing import Any, AsyncIterator


logger = logging.getLogger(__name__)


class CustomAgent:
    def __init__(
        self,
        model_config: ModelConfig,
        name: str,
        instruction: str,
        tools: list[Tool] | None = None,
    ):
        self.session_db_path = model_config.sessions_db_path
        self.model_config = model_config
        self.name = name
        self.instruction = instruction
        self.tools = tools or []

    async def respond(
        self, message: str, context: RequestContext, run_config: RunConfig
    ) -> AsyncIterator[Any]:
        if not message.strip():
            return

        request_logger = bind_logger(
            logger,
            user_id=context.user_id,
            request_id=context.request_id,
        )
        request_logger.info(
            "Invoking %s with %s chars of user input", self.name, len(message)
        )
        session: SQLiteSession = get_session(context.user_id, self.session_db_path)

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
