from agents import Agent, OpenAIProvider, RunConfig, Runner, RunResultStreaming

from .config import Settings
from .finish_dialog import finish_dialog
from .search_index_tools import (
    create_search_index,
    delete_vector_store_file,
    search_in_vector_index,
    upload_vector_store_file,
)
from .upload_files import upload_file

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
    def __init__(self, settings: Settings):
        self.agent = Agent(
            model=settings.model_uri,
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
        )

        self.run_config = RunConfig(
            model_provider=OpenAIProvider(
                api_key=settings.api_key,
                project=settings.folder_id,
                base_url=settings.base_url,
                use_responses=True,
            )
        )

    def invoke(self, message, context, previous_response_id) -> RunResultStreaming:
        return Runner.run_streamed(
            self.agent,
            message,
            context=context,
            run_config=self.run_config,
            previous_response_id=previous_response_id,
        )
