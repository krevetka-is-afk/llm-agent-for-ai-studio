"""Provider-neutral failures exposed by application services."""


class AIStudioRequestError(RuntimeError):
    """Raised when AI Studio rejects or cannot complete an application request."""


class VectorIndexUnavailableError(RuntimeError):
    """Raised when a requested vector index cannot become ready in time."""


__all__ = ["AIStudioRequestError", "VectorIndexUnavailableError"]
