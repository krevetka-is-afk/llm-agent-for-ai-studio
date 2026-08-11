"""Compatibility imports for packaged file policy.

New code must import :mod:`ai_studio_agent_builder.application.file_policy`
directly. This module is removed before the public ``v0.1.0`` release.
"""

from ai_studio_agent_builder.application.file_policy import sanitize_filename

__all__ = ["sanitize_filename"]
