"""Compatibility constructor for the packaged AI interaction application."""

from collections.abc import Callable
from typing import Any

from ai_studio_agent_builder.application.interaction import (
    AgentSpecificationImportError,
    AgentTestInputError,
    AgentTestRequest,
    AgentTestResult,
    Attachment,
    InteractionRequest,
    InteractionResult,
    MAX_AGENT_TEST_INPUT_LENGTH,
    MAX_ATTACHMENTS_PER_REQUEST,
    MAX_TOTAL_UPLOAD_BYTES,
    UPLOAD_RETENTION_POLICY,
    UploadValidationError,
)
from ai_studio_agent_builder.application.interaction_facade import (
    AIInteractionService as PackagedAIInteractionService,
)
from ai_studio_agent_builder.application.ports.agent_runner import (
    AgentRunner,
    AgentRunnerFactory,
)
from ai_studio_agent_builder.application.ports.builder_run import BuilderRunPort
from ai_studio_agent_builder.application.ports.connection import ConnectionValidator
from ai_studio_agent_builder.application.ports.conversation_storage import (
    AttachmentStore,
    ConversationSessionStore,
)
from ai_studio_agent_builder.application.settings import AIServiceConfig
from ai_studio_agent_builder.composition import build_ai_interaction_components
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.client_factory import (
    get_api_key_client,
    get_async_api_key_client,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio.files_gateway import (
    upload_local_file,
)


LegacyAgentRunnerFactory = Callable[[Any, str], AgentRunner]


class AIInteractionService(PackagedAIInteractionService):
    """Preserve the legacy config-first constructor during package migration."""

    def __init__(
        self,
        config: AIServiceConfig,
        *,
        rag_agent: Any | None = None,
        one_prompt_agent: Any | None = None,
        coordinator_agent: Any | None = None,
        agent_runner_factory: LegacyAgentRunnerFactory | None = None,
        builder_run_port: BuilderRunPort | None = None,
        connection_validator: ConnectionValidator | None = None,
        generated_agent_runner_factory: AgentRunnerFactory | None = None,
        attachment_store: AttachmentStore | None = None,
        conversation_session_store: ConversationSessionStore | None = None,
    ) -> None:
        super().__init__(
            build_ai_interaction_components(
                config,
                rag_agent=rag_agent,
                one_prompt_agent=one_prompt_agent,
                coordinator_agent=coordinator_agent,
                agent_runner_factory=agent_runner_factory,
                builder_run_port=builder_run_port,
                connection_validator=connection_validator,
                generated_agent_runner_factory=generated_agent_runner_factory,
                attachment_store=attachment_store,
                conversation_session_store=conversation_session_store,
                sync_client_factory=lambda credentials: get_api_key_client(
                    credentials,
                    config.connection,
                ),
                async_client_factory=lambda credentials: get_async_api_key_client(
                    credentials,
                    config.connection,
                ),
                file_uploader=lambda client, base_dir, filename: upload_local_file(
                    client,
                    base_dir,
                    filename,
                ),
            )
        )


__all__ = [
    "AIInteractionService",
    "AgentSpecificationImportError",
    "AgentTestInputError",
    "AgentTestRequest",
    "AgentTestResult",
    "Attachment",
    "InteractionRequest",
    "InteractionResult",
    "MAX_AGENT_TEST_INPUT_LENGTH",
    "MAX_ATTACHMENTS_PER_REQUEST",
    "MAX_TOTAL_UPLOAD_BYTES",
    "UPLOAD_RETENTION_POLICY",
    "UploadValidationError",
]
