import logging

from agents import RunContextWrapper, function_tool

from ai_studio_agent_builder.builder.context import RequestContext
from ai_studio_agent_builder.domain.routing import ConversationOptions

logger = logging.getLogger(__name__)


def _tool_logger(ctx: RunContextWrapper[RequestContext]) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(
        logger,
        {"user_id": ctx.context.user_id, "request_id": ctx.context.request_id},
    )


@function_tool
def delegate_rag(ctx: RunContextWrapper[RequestContext]) -> str:
    """Route the current request to the RAG specialist agent."""
    tool_logger = _tool_logger(ctx)
    tool_logger.info("Delegate rag tool invoked")
    ctx.context.state.update_state(ConversationOptions.RAG)
    return "TASK DELEGATED TO RAG AGENT"


@function_tool
def delegate_one_prompt(ctx: RunContextWrapper[RequestContext]) -> str:
    """Route the current request to the one-prompt specialist agent."""
    tool_logger = _tool_logger(ctx)
    tool_logger.info("Delegate one_prompt tool invoked")
    ctx.context.state.update_state(ConversationOptions.ONE_PROMPT)
    return "TASK DELEGATED TO ONE PROMPT AGENT"
