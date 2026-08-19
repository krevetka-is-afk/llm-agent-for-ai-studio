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
    CODE_INTERPRETER_WITHOUT_VECTOR_KNOWLEDGE = (
        "code_interpreter_without_vector_knowledge"
    )
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
    r"\bиндекс[а-я]*\s+(?:из|для)\s+файл[а-я]*\b|"
    r"\b(?:ищ[а-я]*|поиск[а-я]*)\s+(?:по|в)\s+"
    r"(?:загруженн[а-я]*\s+)?(?:файл[а-я]*|документ[а-я]*|отчет[а-я]*)\b|"
    r"\bsearch(?:\s+the)?\s+(?:uploaded\s+)?"
    r"(?:files?|documents?|reports?)\b"
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
_CODE_INTERPRETER_TERM = r"(?:code[\s-]?interpreter|интерпретатор[а-я]*\s+кода)"
_CODE_INTERPRETER_REJECTED = re.compile(
    rf"\b(?:без|не\s+(?:нуж[а-я]*|хоч[а-я]*|использ[а-я]*))\s+"
    rf"{_CODE_INTERPRETER_TERM}\b|"
    rf"\b(?:no|without|do\s+not\s+(?:need|want|use)|"
    rf"don't\s+(?:need|want|use))(?:\s+the)?\s+{_CODE_INTERPRETER_TERM}\b"
)
_CODE_INTERPRETER_REQUESTED = re.compile(
    rf"\b{_CODE_INTERPRETER_TERM}\b|"
    r"\b(?:проанализир[а-я]*|обработ[а-я]*|преобраз[а-я]*)"
    r"(?:\s+[а-яa-z0-9.-]+){0,5}\s+(?:csv|xlsx|таблиц[а-я]*)\b|"
    r"\b(?:сдела[а-я]*|постро[а-я]*|выполн[а-я]*)"
    r"(?:\s+[а-яa-z0-9.-]+){0,5}\s+"
    r"(?:расчет[а-я]*|вычислен[а-я]*|график[а-я]*)"
    r"(?:\s+[а-яa-z0-9.-]+){0,6}\s+"
    r"(?:файл[а-я]*|данн[а-я]*|csv|xlsx)\b|"
    r"\b(?:analy[sz]e|process|transform)"
    r"(?:\s+[a-z0-9.-]+){0,5}\s+(?:csv|xlsx|spreadsheet)\b"
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
    if _CODE_INTERPRETER_REJECTED.search(normalized):
        return None
    if _CODE_INTERPRETER_REQUESTED.search(normalized):
        return RoutingDecision(
            ConversationOptions.ONE_PROMPT,
            RoutingReason.CODE_INTERPRETER_WITHOUT_VECTOR_KNOWLEDGE,
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
