import logging

from agents import Agent, OpenAIProvider, RunConfig, Runner
from agents.memory import SQLiteSession
from agents.tool import Tool

from context import RequestContext
from config import ModelConfig

from typing import Any, AsyncIterator

from logging_config import bind_logger
from session import get_session

logger = logging.getLogger(__name__)


class CustomAgent:
    def __init__(self, model_config: ModelConfig, name: str, instruction: str, tools: list[Tool] | None = None):
        self.session_db_path = model_config.sessions_db_path
        self.model_config = model_config
        self.name = name
        self.instruction = instruction
        self.tools = tools or []

    async def respond(self, message, context: RequestContext) -> AsyncIterator[Any]:
        if not message.strip():
            return

        request_logger = bind_logger(
            logger,
            user_id=context.user_id,
        )
        request_logger.info(
            "Invoking ONE-PROMPT agent with %s chars of user input", len(message)
        )
        session: SQLiteSession = get_session(context.user_id, self.session_db_path)

        logging.info(f"Invoke {self.name} model with {message=} {session=}")
        agent = Agent(
            model=f"gpt://{context.folder_id}/{self.model_config.model_name}",
            name=self.name,
            instructions=self.instruction,
            tools=self.tools,
        )
        run_config = RunConfig(
            model_provider=OpenAIProvider(
                api_key=context.access_token,
                project=context.folder_id,
                base_url=self.model_config.base_url,
                use_responses=True,
            ),
        )
        result = Runner.run_streamed(
            starting_agent=agent,
            input=message,
            context=context,
            run_config=run_config,
            session=session,
        )

        async for event in result.stream_events():
            yield event
