import logging

from agents import RunContextWrapper, function_tool
from context import RequestContext

from logging_config import bind_logger

logger = logging.getLogger(__name__)


@function_tool
def finish_dialog(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Call this tool when the conversation is complete and no further
    user interaction is needed.
    Returns message that session is finished.
    """
    tool_logger = bind_logger(logger, user_id=ctx.context.user_id)
    tool_logger.info("Finish dialog tool invoked")
    ctx.context.session_is_done = True
    return "DIALOG_FINISHED"
