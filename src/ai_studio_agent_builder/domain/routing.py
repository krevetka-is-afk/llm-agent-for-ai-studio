import re
from dataclasses import dataclass
from enum import Enum, StrEnum, auto


class ConversationOptions(Enum):
    COORDINATOR = auto()
    RAG = auto()
    ONE_PROMPT = auto()


class RoutingReason(StrEnum):
    RAG_REJECTED = "rag_rejected"
    RAG_REQUESTED = "rag_requested"
    ONE_PROMPT_REQUESTED = "one_prompt_requested"
    WEB_SEARCH_WITHOUT_VECTOR_KNOWLEDGE = "web_search_without_vector_knowledge"
    FILES_REJECTED = "files_rejected"


@dataclass(frozen=True)
class RoutingDecision:
    target: ConversationOptions
    reason: RoutingReason


_RAG_TERM = (
    r"(?:rag|раг|"
    r"векторн[а-я]*\s+(?:поиск[а-я]*|индекс[а-я]*)|"
    r"vector\s+(?:search|index))"
)
_RAG_REJECTED_BEFORE = re.compile(
    rf"(?:\bбез|\bне\s+(?:нуж[а-я]*|хоч[а-я]*|надо|"
    rf"использ[а-я]*|созда[а-я]*))(?:\s+[а-яa-z]+){{0,2}}\s+{_RAG_TERM}\b|"
    rf"\b(?:no|without|do\s+not\s+(?:need|want|use)|"
    rf"don't\s+(?:need|want|use))(?:\s+to\s+use)?\s+{_RAG_TERM}\b"
)
_RAG_REJECTED_AFTER = re.compile(
    rf"\b{_RAG_TERM}(?:\s+[а-яa-z]+){{0,2}}\s+не\s+"
    rf"(?:нуж[а-я]*|хоч[а-я]*|надо|использ[а-я]*)\b|"
    rf"\b{_RAG_TERM}\s+(?:is\s+)?not\s+(?:needed|required|wanted)\b"
)
_RAG_REQUESTED = re.compile(
    rf"\b{_RAG_TERM}\b|"
    r"\bсозда[а-я]*\s+(?:мне\s+)?(?:векторн[а-я]*\s+)?индекс[а-я]*\b|"
    r"\bиндекс[а-я]*\s+(?:из|для)\s+файл[а-я]*\b"
)
_ONE_PROMPT_REQUESTED = re.compile(
    r"\b(?:one[\s-]?prompt|одн[а-я]*[\s-]?промпт[а-я]*)\b"
)
_WEB_SEARCH = re.compile(
    r"\b(?:веб[\s-]?поиск[а-я]*|web[\s-]?search|"
    r"поиск[а-я]*\s+в\s+интернет[а-я]*)\b"
)
_WEB_SEARCH_REJECTED = re.compile(
    r"\bне\s+(?:нуж[а-я]*|хоч[а-я]*|использ[а-я]*)\s+"
    r"(?:веб[\s-]?поиск[а-я]*|поиск[а-я]*\s+в\s+интернет[а-я]*)\b|"
    r"\b(?:no|without|do\s+not\s+need|don't\s+need)\s+web[\s-]?search\b"
)
_FILES_REJECTED = re.compile(
    r"\b(?:пока\s+)?без\s+(?:файл[а-я]*|документ[а-я]*)\b|"
    r"\b(?:файл[а-я]*|документ[а-я]*)\s+не\s+нуж[а-я]*\b"
)


def resolve_explicit_route(message: str | None) -> RoutingDecision | None:
    """Return only high-confidence user routing choices.

    Ambiguous product requirements remain the coordinator's responsibility. Explicit
    vector-search rejection is evaluated before positive terms so a previous RAG route
    cannot override the user's latest choice.
    """
    normalized = _normalize(message)
    if not normalized:
        return None
    if _RAG_REJECTED_BEFORE.search(normalized) or _RAG_REJECTED_AFTER.search(
        normalized
    ):
        return RoutingDecision(
            ConversationOptions.ONE_PROMPT,
            RoutingReason.RAG_REJECTED,
        )
    if _RAG_REQUESTED.search(normalized):
        return RoutingDecision(
            ConversationOptions.RAG,
            RoutingReason.RAG_REQUESTED,
        )
    if _ONE_PROMPT_REQUESTED.search(normalized):
        return RoutingDecision(
            ConversationOptions.ONE_PROMPT,
            RoutingReason.ONE_PROMPT_REQUESTED,
        )
    if _WEB_SEARCH_REJECTED.search(normalized):
        return None
    if _WEB_SEARCH.search(normalized):
        return RoutingDecision(
            ConversationOptions.ONE_PROMPT,
            RoutingReason.WEB_SEARCH_WITHOUT_VECTOR_KNOWLEDGE,
        )
    if _FILES_REJECTED.search(normalized):
        return RoutingDecision(
            ConversationOptions.ONE_PROMPT,
            RoutingReason.FILES_REJECTED,
        )
    return None


def _normalize(message: str | None) -> str:
    if not message:
        return ""
    normalized = message.casefold().replace("ё", "е")
    normalized = re.sub(r"[‐‑‒–—]", "-", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
