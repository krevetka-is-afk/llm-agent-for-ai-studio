"""Provider-neutral failures exposed by application services."""


class AIStudioRequestError(RuntimeError):
    """Raised when AI Studio rejects or cannot complete an application request."""


__all__ = ["AIStudioRequestError"]
