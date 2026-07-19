from context import UserStore


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
