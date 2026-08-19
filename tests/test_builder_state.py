from ai_studio_agent_builder.application.builder_state import ConversationState
from ai_studio_agent_builder.domain.routing import ConversationOptions
from ai_studio_agent_builder.domain.specification import (
    build_code_interpreter_tool_descriptor,
    build_one_prompt_specification,
)


def test_conversation_state_defaults_to_coordinator() -> None:
    assert ConversationState().state is ConversationOptions.COORDINATOR


def test_finish_dialog_keeps_specification_but_reset_clears_it() -> None:
    state = ConversationState(ConversationOptions.RAG)
    state.attach_vector_index(
        index_id="vs_123",
        index_name="knowledge",
        file_ids=("file_1",),
    )

    state.finish_dialog()

    assert state.state is ConversationOptions.COORDINATOR
    assert state.agent_specification is not None

    state.reset_state()

    assert state.state is ConversationOptions.COORDINATOR
    assert state.agent_specification is None


def test_pending_rag_files_survive_copy_commit_and_clear_after_attachment() -> None:
    source = ConversationState(ConversationOptions.RAG)
    source.register_pending_files(
        {
            "file_1": "guide.pdf",
            "file_2": "faq.txt",
        }
    )
    copy = source.copy()
    target = ConversationState()

    target.commit_from(copy)

    assert target.pending_file_ids == ("file_1", "file_2")
    assert target.pending_filenames_by_file_id == {
        "file_1": "guide.pdf",
        "file_2": "faq.txt",
    }

    target.attach_vector_index(
        index_id="vs_123",
        index_name="knowledge",
        file_ids=target.pending_file_ids,
    )

    assert target.pending_file_ids == ()


def test_route_change_preserves_only_tools_supported_by_both_templates() -> None:
    specification = build_one_prompt_specification(
        purpose="Research and calculate",
        instructions="Use the appropriate tools.",
        expected_result="A grounded calculation",
        web_search=True,
        code_interpreter=True,
    )
    state = ConversationState(
        ConversationOptions.ONE_PROMPT,
        draft_agent_specification=specification,
    )

    state.update_state(ConversationOptions.RAG)

    assert state.draft_agent_specification is not None
    assert state.draft_agent_specification.template.value == "rag"
    assert state.draft_agent_specification.tools == (
        build_code_interpreter_tool_descriptor(),
    )
    assert state.latest_agent_specification is None


def test_route_change_without_compatible_tools_keeps_current_reset_behavior() -> None:
    specification = build_one_prompt_specification(
        purpose="Research current events",
        instructions="Search the web.",
        expected_result="A current answer",
        web_search=True,
    )
    state = ConversationState(
        ConversationOptions.ONE_PROMPT,
        draft_agent_specification=specification,
    )

    state.update_state(ConversationOptions.RAG)

    assert state.agent_specification is None
