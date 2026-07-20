import json

from agent_specification import AgentSpecificationStatus
from component_catalog import TemplateId
from conversation_state import ConversationOptions, ConversationState
from custom_agents.one_prompt_agent import ONE_PROMPT_TOOLS_SETUP
from custom_agents.tools.agent_specification import (
    _finalize_agent_specification_impl,
    _update_agent_specification_impl,
)


def test_update_agent_specification_tracks_missing_fields() -> None:
    state = ConversationState(ConversationOptions.ONE_PROMPT)

    result = json.loads(
        _update_agent_specification_impl(
            state,
            purpose="Draft concise support answers",
            instructions="Ask for logs when the issue is unclear.",
        )
    )

    assert result["template"] == TemplateId.ONE_PROMPT.value
    assert result["status"] == AgentSpecificationStatus.NEEDS_CLARIFICATION.value
    assert result["validation"]["missing_fields"] == ["expected_result"]
    assert state.draft_agent_specification is not None
    assert state.latest_agent_specification is None


def test_finalize_agent_specification_promotes_ready_draft() -> None:
    state = ConversationState(ConversationOptions.ONE_PROMPT)
    _update_agent_specification_impl(
        state,
        purpose="Draft concise support answers",
        audience="Support engineers",
        inputs=["customer question"],
        instructions="Ask for logs when the issue is unclear.",
        constraints=["Do not invent product behavior."],
        expected_result="Reusable system prompt",
    )

    result = json.loads(_finalize_agent_specification_impl(state))

    assert result["status"] == AgentSpecificationStatus.READY.value
    assert result["validation"]["missing_fields"] == []
    assert state.latest_agent_specification is state.draft_agent_specification
    assert state.agent_specification is state.latest_agent_specification


def test_updating_finalized_specification_invalidates_previous_export() -> None:
    state = ConversationState(ConversationOptions.ONE_PROMPT)
    _update_agent_specification_impl(
        state,
        purpose="Draft concise support answers",
        instructions="Be concise.",
        expected_result="Reusable system prompt",
    )
    _finalize_agent_specification_impl(state)

    _update_agent_specification_impl(
        state,
        purpose="Draft detailed support answers",
    )

    assert state.latest_agent_specification is None
    assert state.draft_agent_specification is not None
    assert state.agent_specification is state.draft_agent_specification
    assert state.agent_specification.purpose == "Draft detailed support answers"


def test_updating_after_finish_invalidates_previous_export() -> None:
    state = ConversationState(ConversationOptions.ONE_PROMPT)
    _update_agent_specification_impl(
        state,
        purpose="Draft concise support answers",
        instructions="Be concise.",
        expected_result="Reusable system prompt",
    )
    _finalize_agent_specification_impl(state)
    state.finish_dialog()

    _update_agent_specification_impl(
        state,
        purpose="Draft revised support answers",
        instructions="Ask for missing context.",
        expected_result="Revised system prompt",
    )

    assert state.latest_agent_specification is None
    assert state.agent_specification is state.draft_agent_specification
    assert state.agent_specification is not None
    assert state.agent_specification.purpose == "Draft revised support answers"


def test_conversation_state_copy_commit_and_reset_include_specification() -> None:
    source = ConversationState(ConversationOptions.ONE_PROMPT)
    _update_agent_specification_impl(
        source,
        purpose="Draft concise support answers",
        instructions="Be concise.",
        expected_result="Reusable system prompt",
    )
    _finalize_agent_specification_impl(source)
    copy = source.copy()
    copy.finish_dialog()

    target = ConversationState()
    target.commit_from(copy)

    assert target.state is ConversationOptions.COORDINATOR
    assert target.agent_specification is not None
    assert target.agent_specification.status is AgentSpecificationStatus.READY

    target.reset_state()

    assert target.state is ConversationOptions.COORDINATOR
    assert target.agent_specification is None


def test_rag_vector_attachment_contributes_authoritative_components() -> None:
    state = ConversationState(ConversationOptions.RAG)

    state.attach_vector_index(
        index_id="vs_123",
        index_name="knowledge",
        file_ids=("file_1", "file_2"),
    )
    _update_agent_specification_impl(
        state,
        purpose="Answer from uploaded documents",
        instructions="Search the index before answering.",
        expected_result="RAG assistant prompt and connected vector index",
    )
    result = json.loads(_finalize_agent_specification_impl(state))

    assert result["status"] == AgentSpecificationStatus.READY.value
    assert result["template"] == TemplateId.RAG.value
    assert result["parameters"]["index_id"] == "vs_123"
    assert [source["source_id"] for source in result["knowledge_sources"]] == [
        "file_1",
        "file_2",
    ]
    assert result["tools"][0]["tool_id"] == "knowledge_search"


def test_one_prompt_agent_exposes_structured_specification_tools() -> None:
    tool_names = {getattr(tool, "name", None) for tool in ONE_PROMPT_TOOLS_SETUP}

    assert tool_names == {
        "update_agent_specification",
        "finalize_agent_specification",
        "finish_dialog",
    }
