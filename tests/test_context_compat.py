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
