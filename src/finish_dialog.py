import logging

from agents import RunContextWrapper, function_tool
from chatkit.agents import AgentContext

from .logging_config import bind_logger

logger = logging.getLogger(__name__)


@function_tool
def finish_dialog(ctx: RunContextWrapper[AgentContext]) -> str:
    """
    Call this tool when the conversation is complete and no further
    user interaction is needed.
    """
    tool_logger = bind_logger(logger, thread_id=ctx.context.thread.id)
    tool_logger.info("Finish dialog tool invoked")
    ctx.context.request_context['conv_context'].set_done()
    return "DIALOG_FINISHED"
