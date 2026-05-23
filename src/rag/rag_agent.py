import logging

from agents import (
    Agent,
    OpenAIProvider,
    RunConfig,
    Runner,
    RunResultStreaming,
    ModelSettings,
    ModelRetrySettings,
)
from agents.memory import SQLiteSession

from context import RequestContext
from config import AIStudioAuth, ModelConfig, ConnectionConfig
from rag.tools.finish_dialog import finish_dialog
from rag.tools.upload_files import upload_file
from rag.tools.vector_index import (
    create_search_index,
    delete_vector_store_file,
    search_in_vector_index,
    upload_vector_store_file,
)

SUPPORT_AGENT_INSTRUCTIONS = """
You are a helpful support assistant.
You can help users search through their files and create search indexes.

## Tools Available
- `upload_file(filename)` — uploads a file to storage, returns file_id
- `create_vector_index(file_ids, name)` — creates a vector search index with name, returns index_id
- `search_in_vector_index(vector_store_id, query)` - find relevant information from vector store
- `upload_vector_store_file(vector_store_id, file_id)` - attach file to vector store
- `delete_vector_store_file(vector_store_id, file_id)` - delete file from vector store
- `finish_dialog` - finishes dialog after task completed

## Behavior

You are a general assistant. Do NOT guide or instruct the user.
Just have a natural conversation and help with whatever they need.

If the user wants to:

### Create a search index:
- Ask which files they want to index (if not specified)
- Ask all nessasary information from user
- To get file_id upload file into storage using upload_file
- Upload each file using `upload_file`, collect all file_ids
- Call `create_vector_index` with all file_ids
- Tell the user the index is ready and provide index_id
- Tell user about all intermediate steps you've done

## Rules
- Never call `create_vector_index` before all files are uploaded
- If something fails, inform the user briefly and ask how to proceed
- Use the search_vector_store tool to find relevant information before answering
- After achieving user goals ask if user wants to finish dialog
- If user wants to finish dialog call finish_dialog tool and return goodbuy message
""".strip()


class RAGAgent:
    def __init__(
        self,
        auth_config: AIStudioAuth,
        model_config: ModelConfig,
        connection_config: ConnectionConfig,
    ):
        self.agent = Agent(
            model=f"gpt://{auth_config.folder_id}/{model_config.model_name}",
            name="Rag Agent",
            instructions=SUPPORT_AGENT_INSTRUCTIONS,
            tools=[
                upload_file,
                create_search_index,
                finish_dialog,
                search_in_vector_index,
                delete_vector_store_file,
                upload_vector_store_file,
            ],
            model_settings=ModelSettings(
                temperature=model_config.temperature,
                max_tokens=model_config.max_output_tokens,
                verbosity=model_config.verbosity,
                retry=ModelRetrySettings(max_retries=model_config.max_retries),
            ),
        )

        self.run_config = RunConfig(
            model_provider=OpenAIProvider(
                api_key=auth_config.api_key,
                project=auth_config.folder_id,
                base_url=connection_config.base_url,
                use_responses=True,
            ),
        )

    def invoke(
        self, message, context: RequestContext, session: SQLiteSession
    ) -> RunResultStreaming:
        logging.info(f"Invoke model with {message=} {session=}")
        return Runner.run_streamed(
            self.agent,
            message,
            context=context,
            run_config=self.run_config,
            session=session,
        )
