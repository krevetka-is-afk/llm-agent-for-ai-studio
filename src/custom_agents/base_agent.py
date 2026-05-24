import logging

from agents import Agent, OpenAIProvider, RunConfig, Runner
from agents.memory import SQLiteSession
from agents.tool import FunctionTool

from context import RequestContext
from config import Settings

from typing import Any, AsyncIterator

from logging_config import bind_logger
from session import get_session

logger = logging.getLogger(__name__)


class CustomAgent:
    def __init__(self, settings: Settings, name: str, instruction: str, tools: list[FunctionTool] = []):
        self.session_db_path = settings.db_path
        self.name = name
        self.agent = Agent(
            model=settings.model_uri,
            name=name,
            instructions=instruction,
            tools=tools,
        )

        self.run_config = RunConfig(
            model_provider=OpenAIProvider(
                api_key=settings.api_key,
                project=settings.folder_id,
                base_url=settings.base_url,
                use_responses=True,
            ),
        )

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
        result = Runner.run_streamed(
            self.agent,
            message,
            context=context,
            run_config=self.run_config,
            session=session,
        )

        async for event in result.stream_events():
            yield event
