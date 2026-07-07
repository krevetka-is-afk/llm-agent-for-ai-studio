import logging

from agents import RunContextWrapper, function_tool
from context import RequestContext, ConversationOptions

from logging_config import bind_logger

logger = logging.getLogger(__name__)


@function_tool
def delegate_rag(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Call this tool when user need to have Retrieval Augmentation in llm application.
    Specified for RAG llm will solve user promplem.
    Returns success message.
    """
    tool_logger = bind_logger(logger, user_id=ctx.context.user_id)
    tool_logger.info("Delegate rag tool invoked")
    ctx.context.state.update_state(ConversationOptions.RAG)
    return "TASK DELEGATED TO RAG AGENT"


@function_tool
def delegate_one_prompt(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Call this tool when user needs only great prompt in llm application.
    Specified one prompt task llm will solve user promplem.
    Returns success message.
    """
    tool_logger = bind_logger(logger, user_id=ctx.context.user_id)
    tool_logger.info("Delegate one_prompt tool invoked")
    ctx.context.state.update_state(ConversationOptions.ONE_PROMPT)
    return "TASK DELEGATED TO ONE PROMPT AGENT"


@function_tool
def delegate_default_tools_agent(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Call this tool when user needs to add default tool in llm application like web search or image generation.
    Specified llm will solve user promplem.
    Returns success message.
    """
    tool_logger = bind_logger(logger, user_id=ctx.context.user_id)
    tool_logger.info("Delegate default_tools_agent tool invoked")
    ctx.context.state.update_state(ConversationOptions.DEFAULT_TOOLS_AGENT)
    return "TASK DELEGATED TO DEFAULT TOOLS AGENT"
