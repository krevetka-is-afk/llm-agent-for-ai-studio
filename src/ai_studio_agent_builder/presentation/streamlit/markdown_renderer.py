import re
from collections.abc import Callable, Iterator

import streamlit as st


_FENCE_START = re.compile(r"^[ \t]{0,3}(?P<fence>`{3,}|~{3,})")
_INLINE_CODE = re.compile(
    r"(?<!`)(?P<fence>`+)(?!`)(?P<body>.*?)(?<!`)(?P=fence)(?!`)",
    re.DOTALL,
)
_STANDARD_BLOCK_MATH = re.compile(
    r"^[ \t]*\\\[\s*(?P<body>.*?)\s*\\\][ \t]*(?=$|\n)",
    re.DOTALL | re.MULTILINE,
)
_BRACKETED_BLOCK_MATH = re.compile(
    r"^[ \t]*\[\s*(?P<body>[^\n]+?)\s*\][ \t]*(?=$|\n)",
    re.MULTILINE,
)
_INLINE_MATH = re.compile(r"\\\((?P<body>[^\n]*?)\\\)")
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")


def normalize_latex_delimiters(markdown: str) -> str:
    """Convert common model-produced TeX delimiters to Streamlit Markdown syntax."""
    return "".join(
        segment if is_code else _normalize_outside_inline_code(segment)
        for is_code, segment in _fenced_segments(markdown)
    )


def render_markdown(markdown: str) -> None:
    st.markdown(normalize_latex_delimiters(markdown))


def _fenced_segments(markdown: str) -> Iterator[tuple[bool, str]]:
    text_lines: list[str] = []
    code_lines: list[str] = []
    closing_fence: re.Pattern[str] | None = None

    for line in markdown.splitlines(keepends=True):
        if closing_fence is None:
            match = _FENCE_START.match(line)
            if match is None:
                text_lines.append(line)
                continue
            if text_lines:
                yield False, "".join(text_lines)
                text_lines = []
            fence = match.group("fence")
            closing_fence = re.compile(
                rf"^[ \t]{{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*(?:\r?\n)?$"
            )
            code_lines.append(line)
            continue

        code_lines.append(line)
        if closing_fence.match(line):
            yield True, "".join(code_lines)
            code_lines = []
            closing_fence = None

    if code_lines:
        yield True, "".join(code_lines)
    if text_lines:
        yield False, "".join(text_lines)


def _normalize_outside_inline_code(markdown: str) -> str:
    return _replace_outside_matches(markdown, _INLINE_CODE, _normalize_text)


def _replace_outside_matches(
    value: str,
    protected_pattern: re.Pattern[str],
    transform: Callable[[str], str],
) -> str:
    parts: list[str] = []
    previous_end = 0
    for match in protected_pattern.finditer(value):
        parts.append(transform(value[previous_end : match.start()]))
        parts.append(match.group(0))
        previous_end = match.end()
    parts.append(transform(value[previous_end:]))
    return "".join(parts)


def _normalize_text(markdown: str) -> str:
    normalized = _STANDARD_BLOCK_MATH.sub(
        lambda match: _streamlit_block_math(match.group("body")),
        markdown,
    )
    normalized = _BRACKETED_BLOCK_MATH.sub(
        _normalize_bracketed_block,
        normalized,
    )
    return _INLINE_MATH.sub(
        lambda match: f"${match.group('body').strip()}$",
        normalized,
    )


def _normalize_bracketed_block(match: re.Match[str]) -> str:
    body = match.group("body")
    if not _LATEX_COMMAND.search(body):
        return match.group(0)
    return _streamlit_block_math(body)


def _streamlit_block_math(body: str) -> str:
    return f"$$\n{body.strip()}\n$$"
