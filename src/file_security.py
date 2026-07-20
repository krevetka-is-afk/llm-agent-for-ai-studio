import re
from pathlib import Path


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._ -]+")


def sanitize_filename(original_filename: str, *, fallback: str) -> str:
    basename = Path(original_filename.replace("\\", "/")).name
    safe_filename = _UNSAFE_FILENAME_CHARS.sub("_", basename).strip(" .")
    if safe_filename in {"", ".", ".."}:
        return fallback
    return safe_filename
