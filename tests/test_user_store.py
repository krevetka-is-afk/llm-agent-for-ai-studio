import pytest

from src.context import UserStore, UserSecrets
from src.config import AIStudioAuth, _required_env


@pytest.fixture(scope="session")
def user_store():
    return UserStore(AIStudioAuth(
        _required_env("YANDEX_API_KEY"),
        _required_env("YANDEX_FOLDER_ID"),
        "../authorized_key.json",
    ))


@pytest.fixture
def test_user_store_set_api_token(user_store) -> None:
    user_store.set_api_token("test", "Test1")

    result: UserSecrets = user_store.get("test")
    assert result.api_token == 'Test1'

    user_store.set_api_token("test", "test2")

    result: UserSecrets = user_store.get("test")
    assert result.api_token == 'test2'


@pytest.fixture
def test_user_store_set_folder_id(user_store) -> None:
    user_store.set_folder_id("test", "test1")

    result: UserSecrets = user_store.get("test")
    assert result.folder_id == 'test1'

    user_store.set_folder_id("test", "test2")

    result: UserSecrets = user_store.get("test")
    assert result.folder_id == 'test2'
