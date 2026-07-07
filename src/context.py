import logging

from collections import defaultdict
from typing import Optional, Any
from dataclasses import dataclass
from pathlib import Path
from enum import Enum, auto
from openai import OpenAI
import requests
import json

from config import ConnectionConfig, AIStudioAuth
from utils.iam_token import IAMTokenProvider

logger = logging.getLogger(__name__)


def get_user_client(
    user_api_key: str, user_folder_id: str, connection_config: ConnectionConfig
) -> OpenAI:
    return OpenAI(
        api_key=user_api_key,
        project=user_folder_id,
        base_url=connection_config.base_url,
        timeout=connection_config.timeout,
    )


class ConversationOptions(Enum):
    COORDINATOR = auto()
    RAG = auto()
    ONE_PROMPT = auto()


class ConversationState:
    def __init__(self):
        self.state = ConversationOptions.COORDINATOR

    def update_state(self, new_state: ConversationOptions):
        self.state = new_state

    def reset_state(self):
        self.state = ConversationOptions.COORDINATOR


@dataclass
class UserSecrets:
    api_token: Optional[str] = None
    folder_id: Optional[str] = None


class UserStore:
    def __init__(self, config: AIStudioAuth):
        self.conv = defaultdict(ConversationState)
        self.iam_provider = IAMTokenProvider(config.authorized_keys_path)
        self.folder_id = config.folder_id
        self.base_url = "https://lockbox.api.cloud.yandex.net/lockbox/v1/secrets"

    def get(self, user_id: str) -> UserSecrets:
        _, labels = self._get_user_secret(user_id)
        return UserSecrets(
            api_token=self._decode_key(labels.get('api_token')),
            folder_id=labels.get('folder_id'),
        )

    def get_state(self, user_id: str) -> ConversationState:
        return self.conv[user_id]

    def set_api_token(self, user_id: str, api_token: str) -> None:
        id, labels = self._get_user_secret(user_id)
        labels['api_token'] = self._encode_key(api_token)
        if id is None:
            self._create_user_secret(user_id, labels)
        else:
            self._update_user_secret(id, labels)

    def set_folder_id(self, user_id: str, folder_id: str) -> None:
        id, labels = self._get_user_secret(user_id)
        labels['folder_id'] = folder_id
        if id is None:
            self._create_user_secret(user_id, labels)
        else:
            self._update_user_secret(id, labels)

    def _get_user_secret(self, user_id: str) -> tuple[Any, Any]:
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.iam_provider.create_iam_token()}",
        }
        response = requests.get(
            url=self.base_url,
            headers=header,
            params={"folder_id": self.folder_id},
            timeout=1,
        )
        secrets = json.loads(response.text)['secrets']
        for secret in secrets:
            if secret.get('name') == user_id:
                return secret.get('id'), secret.get('labels', {})
        return None, {}

    def _create_user_secret(self, user_id: str, labels: dict) -> None:
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.iam_provider.create_iam_token()}",
        }
        payloads = {
            "folder_id": self.folder_id,
            "name": user_id,
            "labels": labels,
        }

        response = requests.post(
            url=self.base_url,
            headers=header,
            json=payloads,
            timeout=1,
        )

        response.raise_for_status()

    def _update_user_secret(self, secret_id: str, labels: dict) -> None:
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.iam_provider.create_iam_token()}",
        }
        response = requests.patch(
            url=f"{self.base_url}/{secret_id}",
            headers=header,
            data=json.dumps({"update_mask": "labels", "labels": labels}),
            timeout=1,
        )

        response.raise_for_status()

    def _encode_key(self, key: str) -> str | None:
        mask = 0

        for i, ch in enumerate(key):
            if ch.isupper():
                mask |= 1 << i

        return key.lower() + "_" + str(mask)

    def _decode_key(self, key: str | None) -> str | None:
        if key is None:
            return None
        lower_key, mask = key.split("_")
        mask = int(mask)
        chars = list(lower_key)
        for i in range(len(chars)):
            if mask & (1 << i):
                chars[i] = chars[i].upper()
        return ''.join(chars)


@dataclass
class RequestContext:
    user_id: str
    user_files_dir: Path
    client: OpenAI
    state: ConversationState
