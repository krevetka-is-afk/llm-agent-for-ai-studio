"""Application orchestration for compiling and testing generated agents."""

import asyncio
import hashlib
import logging
import time
from collections.abc import Mapping
from typing import Any

from ai_studio_agent_builder.application.interaction import (
    AgentTestInputError,
    AgentTestRequest,
    AgentTestResult,
    MAX_AGENT_TEST_INPUT_LENGTH,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentProviderError,
    AgentRunPreview,
    AgentRunnerError,
    AgentRunnerFactory,
)
from ai_studio_agent_builder.domain.runtime import (
    AgentRuntimeCompilationError,
    AgentRuntimeSettings,
    ExecutableAgentConfig,
    compile_agent_specification,
)
from ai_studio_agent_builder.domain.specification import (
    AgentSpecification,
    InvalidSpecificationRecordError,
)
from ai_studio_agent_builder.domain.specification_codec import (
    load_agent_specification,
)


logger = logging.getLogger(__name__)


class AgentPreviewService:
    def __init__(
        self,
        runtime_settings: AgentRuntimeSettings,
        runner_factory: AgentRunnerFactory,
    ) -> None:
        self._runtime_settings = runtime_settings
        self._runner_factory = runner_factory

    async def test_agent_specification(
        self,
        request: AgentTestRequest,
    ) -> AgentTestResult:
        user_input = request.user_input.strip()
        if not user_input:
            raise AgentTestInputError("Agent test input must not be empty")
        if len(user_input) > MAX_AGENT_TEST_INPUT_LENGTH:
            raise AgentTestInputError(
                f"Agent test input exceeds {MAX_AGENT_TEST_INPUT_LENGTH} characters"
            )

        request_logger = logging.LoggerAdapter(
            logger,
            {
                "user_id": _pseudonymous_user_id(request.user_id),
                "request_id": request.request_id,
            },
        )
        started_at = time.monotonic()
        try:
            specification = load_agent_specification(request.specification_record)
            executable_config = self.prepare_agent_runtime(
                request.specification_record,
                specification=specification,
            )
            native_tool_types = tuple(
                tool["type"]
                for tool in executable_config.tools
                if isinstance(tool.get("type"), str)
            )
            request_logger.info(
                "Generated agent test started template=%s tools=%s",
                specification.template.value,
                native_tool_types,
            )
            runner = self._runner_factory.create(request.credentials)
            preview = await asyncio.to_thread(
                runner.run,
                executable_config,
                user_input,
            )
        except (
            InvalidSpecificationRecordError,
            AgentRuntimeCompilationError,
            AgentRunnerError,
        ) as exc:
            request_logger.warning(
                "Generated agent test failed category=%s duration_ms=%d",
                type(exc).__name__,
                _duration_ms(started_at),
            )
            raise
        except Exception as exc:
            request_logger.error(
                "Generated agent test failed category=unexpected duration_ms=%d",
                _duration_ms(started_at),
            )
            raise AgentProviderError() from exc
        request_logger.info(
            "Generated agent test completed response_id=%s duration_ms=%d",
            preview.response_id,
            _duration_ms(started_at),
        )
        return _agent_test_result(preview)

    def prepare_agent_runtime(
        self,
        specification_record: Mapping[str, Any],
        *,
        specification: AgentSpecification | None = None,
    ) -> ExecutableAgentConfig:
        trusted_specification = specification or load_agent_specification(
            specification_record
        )
        return compile_agent_specification(
            trusted_specification,
            runtime=self._runtime_settings,
        )


def _agent_test_result(preview: AgentRunPreview) -> AgentTestResult:
    return AgentTestResult(
        response_id=preview.response_id,
        output_text=preview.output_text,
        citations=preview.citations,
        input_tokens=preview.input_tokens,
        output_tokens=preview.output_tokens,
        total_tokens=preview.total_tokens,
    )


def _pseudonymous_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


def _duration_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


__all__ = ["AgentPreviewService"]
