import logging

from agents import RunContextWrapper, function_tool
from context import RequestContext, ConversationOptions

from logging_config import bind_logger

logger = logging.getLogger(__name__)


@function_tool
def delegate_rag(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Call this tool when the conversation is complete and no further
    user interaction is needed.
    Returns message that session is finished.
    """
    tool_logger = bind_logger(logger, user_id=ctx.context.user_id)
    tool_logger.info("Delegate rag tool invoked")
    ctx.context.state.update_state(ConversationOptions.RAG)
    return "TASK DELEGATED TO RAG AGENT"


@function_tool
def delegate_one_prompt(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Call this tool when the conversation is complete and no further
    user interaction is needed.
    Returns message that session is finished.
    """
    tool_logger = bind_logger(logger, user_id=ctx.context.user_id)
    tool_logger.info("Delegate one_prompt tool invoked")
    ctx.context.state.update_state(ConversationOptions.ONE_PROMPT)
    return "TASK DELEGATED TO ONE PROMPT AGENT"
