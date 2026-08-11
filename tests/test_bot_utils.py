from ai_studio_agent_builder.presentation.telegram.media import (
    sanitize_download_filename,
)


def test_telegram_filename_is_reduced_to_a_safe_basename() -> None:
    assert sanitize_download_filename("..\\..// bad:\x00name?.txt ") == "bad_name_.txt"
    assert sanitize_download_filename("../..") == "download.bin"
