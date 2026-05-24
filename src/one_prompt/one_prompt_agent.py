import logging

from agents import Agent, OpenAIProvider, RunConfig, Runner, RunResultStreaming
from agents.memory import SQLiteSession

from context import RequestContext
from config import Settings
from common_tools.finish_dialog import finish_dialog

ONE_PROMPT_AGENT_INSTRUCTIONS = """
You are a helpful assistant whose job is to help the user craft a **system‑prompt** for their own LLM‑application model.  
Your workflow must follow these steps:

1. **Review the conversation history** that the user provides (or that you have in context) and extract the key requirements, constraints, style, and any domain‑specific information that the user wants the future LLM to follow.

2. **Draft a concise, clear system‑prompt** that captures all of those requirements.  
   - The prompt should be a single paragraph (or a short list of bullet points if the user prefers) that can be directly used as the `system` message when the user sends a request to their own model.  
   - Use plain language, avoid unnecessary jargon, and make sure every requirement extracted in step 1 appears in the draft.

3. **Present the draft to the user** and ask for confirmation**
4. **Iterate**:  
- If the user replies with a request for changes, modify the prompt accordingly, then go back to step 3.  
- Keep iterating until the user explicitly confirms that the prompt is ready.

5. **Finish the dialog**:  
- Once the user has confirmed the prompt, you must call the tool **`finish_dialog`** with **no arguments**.  
- Return the tool’s output directly as your final response (do not add extra text after the tool call).

**Additional guidelines**

- **Stay on topic** – focus only on building the system‑prompt; do not drift into unrelated conversation.
- **Be concise** – keep your explanations short; the user only needs the prompt and confirmation.
- **Ask clarifying questions only when necessary** – if the conversation history is ambiguous, ask the user for the missing detail before drafting the prompt.
- **Never fabricate** a tool call; only call `finish_dialog` when you have received an explicit “Yes, it’s ready.” from the user.

""".strip()


class OnePromptAgent:
    def __init__(self, settings: Settings):
        self.agent = Agent(
            model=settings.model_uri,
            name="Rag Agent",
            instructions=ONE_PROMPT_AGENT_INSTRUCTIONS,
            tools=[
                finish_dialog
            ]
        )

        self.run_config = RunConfig(
            model_provider=OpenAIProvider(
                api_key=settings.api_key,
                project=settings.folder_id,
                base_url=settings.base_url,
                use_responses=True,
            ),
        )

    def invoke(self, message, context: RequestContext, session: SQLiteSession) -> RunResultStreaming:
        logging.info(f"Invoke model with {message=} {session=}")
        return Runner.run_streamed(
            self.agent,
            message,
            context=context,
            run_config=self.run_config,
            session=session,
        )
