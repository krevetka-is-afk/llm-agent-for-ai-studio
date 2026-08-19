import io
import json
import logging
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from openai.types.responses import ResponseTextDeltaEvent

from ai_studio_agent_builder.domain.content_policy import (
    ensure_model_output_allowed,
)

from ..result_assembly import AgentRunResult, ToolExecution


logger = logging.getLogger(__name__)


class AgentRunCollector:
    """Normalize Agents SDK stream events into a provider-neutral run result."""

    def __init__(self) -> None:
        self._text = io.StringIO()
        self._policy_tail = ""
        self._calls: dict[str, ToolExecution] = {}
        self._call_order: list[str] = []
        self._anonymous_call_number = 0

    def consume(self, event: Any) -> None:
        if event.type == "raw_response_event" and isinstance(
            event.data, ResponseTextDeltaEvent
        ):
            self._text.write(event.data.delta)
            self._policy_tail = (self._policy_tail + event.data.delta)[-4_096:]
            ensure_model_output_allowed(self._policy_tail)
            return
        if event.type != "run_item_stream_event":
            return
        if event.name == "tool_called":
            self._consume_tool_call(event.item)
        elif event.name == "tool_output":
            self._consume_tool_output(event.item)

    def build(self) -> AgentRunResult:
        ensure_model_output_allowed(self._text.getvalue())
        return AgentRunResult(
            text=self._text.getvalue(),
            tool_executions=tuple(self._calls[key] for key in self._call_order),
        )

    def _consume_tool_call(self, item: Any) -> None:
        raw_item = item.raw_item
        call_id = self._value(raw_item, "call_id") or self._value(raw_item, "id")
        if not isinstance(call_id, str) or not call_id:
            call_id = f"anonymous-{self._anonymous_call_number}"
            self._anonymous_call_number += 1
        name = self._value(raw_item, "name")
        if not isinstance(name, str) or not name:
            return
        arguments = self._parse_arguments(
            self._value(raw_item, "arguments"),
            call_id=call_id,
            tool_name=name,
        )
        if call_id not in self._calls:
            self._call_order.append(call_id)
        self._calls[call_id] = ToolExecution(
            call_id=call_id,
            name=name,
            arguments=arguments,
        )

    def _consume_tool_output(self, item: Any) -> None:
        raw_item = item.raw_item
        call_id = self._value(raw_item, "call_id") or self._value(raw_item, "id")
        if not isinstance(call_id, str) or call_id not in self._calls:
            return
        self._calls[call_id] = replace(
            self._calls[call_id],
            output=item.output,
        )

    @staticmethod
    def _parse_arguments(value: Any, *, call_id: str, tool_name: str) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if not isinstance(value, str):
            logger.warning(
                "Malformed tool arguments call_id=%s tool=%s reason=not-string-or-mapping",
                call_id,
                tool_name,
            )
            return {}
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            logger.warning(
                "Malformed tool arguments call_id=%s tool=%s reason=invalid-json",
                call_id,
                tool_name,
            )
            return {}
        if not isinstance(parsed, Mapping):
            logger.warning(
                "Malformed tool arguments call_id=%s tool=%s reason=not-object",
                call_id,
                tool_name,
            )
            return {}
        return dict(parsed)

    @staticmethod
    def _value(source: Any, name: str) -> Any:
        if isinstance(source, Mapping):
            return source.get(name)
        return getattr(source, name, None)


__all__ = ["AgentRunCollector"]
