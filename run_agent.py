from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI

from rag_agent.rag_tools_schema import RAG_TOOLS_SCHEMA
from rag_agent.rag_utils import build_vector_store, search_vector_store
from tracer import ToolTracer


@dataclass
class AgentContext:
    query: str
    vector_stores: set = field(default_factory=set)
    files: set = field(default_factory=set)


def handle_tool_call(
    tool_call,
    client: OpenAI,
    ctx: AgentContext,
    tracer: ToolTracer,
    prev_message_id: int | None = None,
):
    name = tool_call.get("name")
    args = tool_call.get("args")
    if name == "build_vector_store_tool":
        vector_store_id = build_vector_store(
            client=client,
            name=args.get("name", ""),
            files=[Path(p) for p in args.get("files", [])],
        )
        ctx.vector_stores.add(vector_store_id)
        result = vector_store_id
    elif name == "search_vector_store_tool":
        result = "\n".join(
            search_vector_store(
                client=client,
                vector_store_id=args.get("vector_store_id"),
                query=args.get("query", ""),
                limit=args.get("limit", 1),
            )
        )
    else:
        raise ValueError(f"Unknown tool: {name}")

    tracer.record(name, args, result)
    return ToolMessage(
        content=str(result),
        tool_call_id=tool_call.get("id"),
        name=name,
        id=prev_message_id,
    )


SYSTEM_PROMPT = """\
You are a helpful assistant that can work with document files using tools.

You have access to two tools:

1. build_vector_store_tool
   - Use this tool to create a vector store (semantic index) from one or more available files.
   - Parameters:
     - name: a short human-readable name for the vector store
     - files: a list of file paths

2. search_vector_store_tool
   - Use this tool to search an existing vector store using a natural-language query.
   - Parameters:
     - vector_store_id: the ID of the vector store to search
     - query: the search query

Available files:
[FILES]

Instructions:
- Only use files from the available files list above.
- Never invent new file names or paths that are not in the available files list.
- The user may refer to files imprecisely, using shortened names, partial paths, or small mistakes. Match the user's intent to the closest available file paths whenever the intended files are reasonably clear.
- If the user asks to use "all files", "everything", "all documents", or does not specify concrete files when asking to build an index, assume they want to use all available files.
- If the user asks to create an index/vector store, call build_vector_store_tool.
- If the user asks to search in an already created vector store, call search_vector_store_tool.
- If the user asks to create an index and then search it, first call build_vector_store_tool, then call search_vector_store_tool with the returned vector_store_id.
- If the user's file reference is too ambiguous to match confidently, ask for clarification instead of guessing.
- Do not claim that a tool was used unless it was actually called.
- After all necessary tool calls are completed, always provide a final natural-language response summarizing what you did and the result.
- Be concise, accurate, and follow the user's request.
"""


def run_rag_agent(
    client: OpenAI,
    llm: ChatOpenAI,
    user_message: str,
    files: list[Path],
    history: list = [],
    ctx: AgentContext | None = None,
    tracer: ToolTracer | None = None,
    max_tool_calls: int = 3,
) -> str:
    if ctx is None:
        ctx = AgentContext(query=user_message)
    if tracer is None:
        tracer = ToolTracer()

    ctx.files |= set(files)

    system_prompt_with_files = SYSTEM_PROMPT.replace(
        "[FILES]", "\n".join([str(file) for file in sorted(list(ctx.files))])
    )
    history.extend(
        [
            SystemMessage(content=system_prompt_with_files),
            HumanMessage(content=user_message),
        ]
    )
    msg = llm.bind_tools(RAG_TOOLS_SCHEMA).invoke(history)
    history.append(msg)

    while hasattr(msg, "tool_calls") and msg.tool_calls and max_tool_calls > 0:
        max_tool_calls -= 1
        for tool_call in msg.tool_calls:
            tool_message = handle_tool_call(
                tool_call, client, ctx, tracer=tracer, prev_message_id=history[-1].id
            )
            history.append(tool_message)

        msg = llm.bind_tools(RAG_TOOLS_SCHEMA).invoke(history)
        history.append(msg)
    return msg.content, history, ctx, tracer
