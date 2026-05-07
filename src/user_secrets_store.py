from collections import defaultdict
from dataclasses import dataclass
from typing import Optional


@dataclass
class UserSecrets:
    api_token: Optional[str] = None
    folder_id: Optional[str] = None


class UserSecretsStore:
    def __init__(self):
        self._data: defaultdict[str, UserSecrets] = defaultdict(UserSecrets)

    def get(self, user_id: str) -> UserSecrets:
        return self._data[user_id]

    def set_api_token(self, user_id: str, api_token: str) -> None:
        self._data[user_id].api_token = api_token

    def set_folder_id(self, user_id: str, folder_id: str) -> None:
        self._data[user_id].folder_id = folder_id
