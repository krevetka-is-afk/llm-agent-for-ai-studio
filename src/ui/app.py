"""Compatibility executable for the packaged Streamlit web entrypoint."""

from ai_studio_agent_builder.composition import configure_web_logging
from ai_studio_agent_builder.entrypoints.web import main
from ai_studio_agent_builder.presentation.streamlit.uploads import (
    attachment_record as _attachment_record,
    validate_uploaded_files as _validate_uploaded_files,
)


__all__ = ["_attachment_record", "_validate_uploaded_files", "main"]

if __name__ == "__main__":
    configure_web_logging()
    main()
