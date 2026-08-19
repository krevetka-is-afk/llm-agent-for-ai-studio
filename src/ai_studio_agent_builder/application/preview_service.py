"""Application orchestration for compiling and testing generated agents."""

import asyncio
import hashlib
import logging
import time
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from ai_studio_agent_builder.application.file_lifecycle import (
    PreviewInputFileLifecycle,
    PreviewOutputFileLifecycle,
)
from ai_studio_agent_builder.application.interaction import (
    AgentTestInputError,
    AgentTestRequest,
    AgentTestResult,
    GeneratedFile,
    GeneratedFileWarning,
    MAX_AGENT_TEST_INPUT_LENGTH,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentProviderError,
    AgentRunPreview,
    AgentRunnerError,
    AgentRunnerFactory,
)
from ai_studio_agent_builder.domain.content_policy import (
    POLICY_REFUSAL_MESSAGE,
    assess_model_output,
    assess_user_content,
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
        input_file_lifecycle: PreviewInputFileLifecycle,
        output_file_lifecycle: PreviewOutputFileLifecycle,
    ) -> None:
        self._runtime_settings = runtime_settings
        self._runner_factory = runner_factory
        self._input_file_lifecycle = input_file_lifecycle
        self._output_file_lifecycle = output_file_lifecycle

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
        input_decision = assess_user_content(
            user_input,
            request.specification_record,
            tuple(
                value
                for attachment in request.attachments
                for value in (
                    attachment.caption,
                    attachment.display_name,
                    attachment.filename,
                )
                if value is not None
            ),
        )
        if input_decision.violation is not None:
            logger.warning(
                "Generated agent test blocked by content policy reason=%s",
                input_decision.violation.value,
            )
            raise AgentTestInputError(POLICY_REFUSAL_MESSAGE)

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
            preview, generated_files, generated_file_warnings = await asyncio.to_thread(
                self._run_preview,
                request,
                executable_config,
                user_input,
            )
        except (
            AgentTestInputError,
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
        return _agent_test_result(
            preview,
            generated_files=generated_files,
            generated_file_warnings=generated_file_warnings,
        )

    def _run_preview(
        self,
        request: AgentTestRequest,
        executable_config: ExecutableAgentConfig,
        user_input: str,
    ) -> tuple[
        AgentRunPreview,
        tuple[GeneratedFile, ...],
        tuple[GeneratedFileWarning, ...],
    ]:
        with self._input_file_lifecycle.bind_inputs(
            request,
            executable_config,
        ) as request_config:
            runner = self._runner_factory.create(request.credentials)
            preview = runner.run(request_config, user_input)
            output_decision = assess_model_output(
                preview.output_text,
                preview.citations,
                preview.generated_artifacts,
            )
            if output_decision.violation is not None:
                logger.warning(
                    "Generated agent output blocked by content policy reason=%s",
                    output_decision.violation.value,
                )
                warnings = self._output_file_lifecycle.discard_outputs(
                    request,
                    preview,
                )
                return (
                    replace(
                        preview,
                        output_text=POLICY_REFUSAL_MESSAGE,
                        citations=(),
                        generated_artifacts=(),
                        container_ids=(),
                    ),
                    (),
                    warnings,
                )
            generated_files, warnings = self._output_file_lifecycle.materialize_outputs(
                request,
                preview,
            )
            return preview, generated_files, warnings

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


def _agent_test_result(
    preview: AgentRunPreview,
    *,
    generated_files: tuple[GeneratedFile, ...],
    generated_file_warnings: tuple[GeneratedFileWarning, ...],
) -> AgentTestResult:
    return AgentTestResult(
        response_id=preview.response_id,
        output_text=preview.output_text,
        citations=preview.citations,
        input_tokens=preview.input_tokens,
        output_tokens=preview.output_tokens,
        total_tokens=preview.total_tokens,
        generated_files=generated_files,
        generated_file_warnings=generated_file_warnings,
    )


def _pseudonymous_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]


def _duration_ms(started_at: float) -> int:
    return max(0, round((time.monotonic() - started_at) * 1000))


__all__ = ["AgentPreviewService"]
