import logging

from agents import RunContextWrapper, function_tool
from chatkit.agents import AgentContext


@function_tool
def finish_dialog(ctx: RunContextWrapper[AgentContext]) -> str:
    """
    Call this tool when the conversation is complete and no further
    user interaction is needed.
    """
    logging.info("Finish dialog tool")
    ctx.context.request_context['conv_context'].set_done()
    return "DIALOG_FINISHED"
