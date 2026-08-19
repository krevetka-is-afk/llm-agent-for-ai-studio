import logging

from agents import RunContextWrapper, function_tool

from ai_studio_agent_builder.builder.context import RequestContext

logger = logging.getLogger(__name__)


@function_tool
def finish_dialog(ctx: RunContextWrapper[RequestContext]) -> str:
    """
    Call this tool when the conversation is complete and no further
    user interaction is needed.
    Returns message that session is finished.
    """
    tool_logger = logging.LoggerAdapter(
        logger,
        {"user_id": ctx.context.user_id, "request_id": ctx.context.request_id},
    )
    tool_logger.info("Finish dialog tool invoked")
    ctx.context.state.finish_dialog()
    return "DIALOG_FINISHED"
