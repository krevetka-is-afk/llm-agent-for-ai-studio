"""Compatibility imports for packaged builder result handling.

New code must import from :mod:`ai_studio_agent_builder.builder` directly.
This module is removed before the public ``v0.1.0`` release.
"""

from ai_studio_agent_builder.builder.agents.sdk_event_adapter import AgentRunCollector
from ai_studio_agent_builder.builder.result_assembly import (
    AgentRunResult,
    AgentSpecificationResultPart,
    IndexedFileResult,
    MarkdownResultPart,
    ResultAssembler,
    ResultPart,
    ToolExecution,
    VectorIndexResultPart,
    merge_agent_runs,
    render_result_text,
    result_part_to_record,
)

__all__ = [
    "AgentRunCollector",
    "AgentRunResult",
    "AgentSpecificationResultPart",
    "IndexedFileResult",
    "MarkdownResultPart",
    "ResultAssembler",
    "ResultPart",
    "ToolExecution",
    "VectorIndexResultPart",
    "merge_agent_runs",
    "render_result_text",
    "result_part_to_record",
]
