from context import (
    AIStudioCredentials,
    ConversationOptions,
    ConversationState,
    RequestContext,
    UserCredentials,
    UserStore,
    get_api_key_client,
    get_async_api_key_client,
)


def test_context_keeps_public_compatibility_exports() -> None:
    assert AIStudioCredentials
    assert UserCredentials
    assert ConversationOptions
    assert ConversationState
    assert UserStore
    assert RequestContext
    assert callable(get_api_key_client)
    assert callable(get_async_api_key_client)


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
