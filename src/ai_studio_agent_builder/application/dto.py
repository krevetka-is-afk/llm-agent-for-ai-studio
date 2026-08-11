from dataclasses import dataclass


@dataclass(frozen=True)
class AIStudioCredentials:
    api_key: str
    folder_id: str


@dataclass(frozen=True)
class UserCredentials:
    """Legacy OAuth gateway contract kept outside the manual API-key flow."""

    access_token: str
    folder_id: str
