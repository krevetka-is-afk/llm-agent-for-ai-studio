from ai_studio_agent_builder.infrastructure.persistence.telegram_user_store import (
    UserStore,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_pending_credentials_become_active_only_after_validation() -> None:
    store = UserStore()
    user_id = "42"

    store.set_pending_api_token(user_id, "AQAAAA-secret", message_id=10)
    assert store.get_pending_credentials(user_id) is None
    assert store.get(user_id).api_token is None

    store.set_pending_folder_id(user_id, "b1gfolder", message_id=11)
    message_ids = store.activate_pending_credentials(user_id)

    active = store.get(user_id)
    assert active.api_token == "AQAAAA-secret"
    assert active.folder_id == "b1gfolder"
    assert message_ids == (10, 11)
    assert store.get_pending_credentials(user_id) is None


def test_replaced_pending_secret_messages_are_deleted_after_success() -> None:
    store = UserStore()
    user_id = "42"

    store.set_pending_api_token(user_id, "AQAAAA-old", message_id=10)
    store.set_pending_api_token(user_id, "AQAAAA-current", message_id=11)
    store.set_pending_folder_id(user_id, "b1gfolder", message_id=12)

    assert store.activate_pending_credentials(user_id) == (10, 11, 12)
    assert store.get(user_id).api_token == "AQAAAA-current"


def test_pending_credentials_expire_after_ttl() -> None:
    clock = FakeClock()
    store = UserStore(pending_ttl_seconds=30, monotonic=clock)

    store.set_pending_api_token("42", "AQAAAA-secret", message_id=10)
    store.set_pending_folder_id("42", "folder", message_id=11)
    clock.now = 31

    assert store.get_pending_credentials("42") is None
    assert store.clear_pending_message_ids("42") == (10, 11)


def test_clear_credentials_removes_active_pending_and_conversation_state() -> None:
    store = UserStore()
    store.set_pending_api_token("42", "AQAAAA-secret", message_id=10)
    store.set_pending_folder_id("42", "folder", message_id=11)
    store.activate_pending_credentials("42")
    store.get_state("42").update_state(store.get_state("42").state.RAG)
    store.set_pending_api_token("42", "AQAAAA-new", message_id=12)

    message_ids = store.clear_credentials("42")

    assert message_ids == (12,)
    assert store.get("42").api_token is None
    assert store.get("42").folder_id is None
    assert store.get_pending_credentials("42") is None
    assert store.get_state("42").state.name == "COORDINATOR"
