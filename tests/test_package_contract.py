import agent_runner as legacy_agent_runner
import ai_interaction_service as legacy_interaction
import agent_runtime as legacy_runtime
import agent_specification as legacy_specification
import bot_handlers as legacy_bot_handlers
import bot_utils as legacy_bot_utils
import component_catalog as legacy_catalog
import conversation_state as legacy_builder_state
import config as legacy_config
import credentials as legacy_credentials
import custom_agents.base_agent as legacy_base_agent
import custom_agents.coordinator_agent as legacy_coordinator_agent
import custom_agents.one_prompt_agent as legacy_one_prompt_agent
import custom_agents.rag_agent as legacy_rag_agent
import custom_agents.tools.agent_specification as legacy_specification_tools
import custom_agents.tools.delegate_tools as legacy_delegate_tools
import custom_agents.tools.finish_dialog as legacy_finish_dialog
import custom_agents.tools.upload_files as legacy_upload_files
import custom_agents.tools.vector_index as legacy_vector_index
import file_security as legacy_file_security
import logging_config as legacy_logging
import message_service as legacy_messages
import request_context as legacy_request_context
import result_assembly as legacy_result_assembly
import routing as legacy_routing
import session as legacy_agent_sessions
import telegram_flow as legacy_telegram_flow
import telegram_session as legacy_telegram_session
import ui.agent_test_panel as legacy_agent_test_panel
import ui.api_key_store as legacy_api_key_store
import ui.attachments as legacy_attachments
import ui.chat_flow as legacy_chat_flow
import ui.connection as legacy_connection
import ui.developer_bundle as legacy_developer_bundle
import ui.result_view as legacy_result_view
import ui.uploads as legacy_uploads
import ui.user_guidance as legacy_user_guidance
import user_store as legacy_user_store
import yandex_responses_runner as legacy_yandex_runner

import ai_studio_agent_builder as public_api
from ai_studio_agent_builder import config
from ai_studio_agent_builder.application import (
    builder_service,
    builder_state,
    dto,
    errors,
    file_lifecycle,
    file_policy,
    interaction,
    interaction_facade,
    preview_service,
    settings,
)
from ai_studio_agent_builder.application.ports import (
    agent_runner,
    api_key_store as api_key_port,
    builder_run,
    connection as connection_port,
    conversation_storage,
)
from ai_studio_agent_builder.builder import context as builder_context
from ai_studio_agent_builder.builder import result_assembly
from ai_studio_agent_builder.builder.agents import run_adapter, sdk_event_adapter
from ai_studio_agent_builder.builder.agents import (
    base_agent,
    coordinator_agent,
    one_prompt_agent,
    rag_agent,
)
from ai_studio_agent_builder.builder.agents.tools import (
    agent_specification as specification_tools,
    delegate_tools,
    finish_dialog,
    vector_index,
)
from ai_studio_agent_builder.domain import (
    catalog,
    routing,
    runtime,
    specification,
    specification_codec,
)
from ai_studio_agent_builder.infrastructure.persistence import (
    agent_sessions,
    api_key_store,
    local_attachments,
    telegram_user_store,
)
from ai_studio_agent_builder.infrastructure.observability import (
    logging as observability,
)
from ai_studio_agent_builder.infrastructure.yandex_ai_studio import (
    client_factory,
    connection as provider_connection,
    files_gateway,
    responses_runner,
)
from ai_studio_agent_builder.presentation.streamlit import (
    agent_test_panel,
    attachments,
    chat_flow,
    connection,
    developer_bundle,
    result_view,
    uploads,
    user_guidance,
)
from ai_studio_agent_builder.presentation.telegram import (
    handlers as telegram_handlers,
    http_session as telegram_http_session,
    media as telegram_media,
    messages as telegram_messages,
    request_gate as telegram_request_gate,
)


def test_public_api_reexports_stable_domain_contracts() -> None:
    assert public_api.AgentSpecification is specification.AgentSpecification
    assert public_api.AgentSpecificationStatus is specification.AgentSpecificationStatus
    assert public_api.ExecutableAgentConfig is runtime.ExecutableAgentConfig
    assert public_api.KnowledgeSource is specification.KnowledgeSource
    assert public_api.TemplateId is catalog.TemplateId
    assert public_api.ToolDescriptor is specification.ToolDescriptor
    assert public_api.compile_agent_specification is runtime.compile_agent_specification
    assert (
        public_api.dump_agent_specification
        is specification_codec.dump_agent_specification
    )
    assert (
        public_api.dumps_agent_specification
        is specification_codec.dumps_agent_specification
    )
    assert (
        public_api.load_agent_specification
        is specification_codec.load_agent_specification
    )
    assert (
        public_api.loads_agent_specification
        is specification_codec.loads_agent_specification
    )
    assert errors.AIStudioRequestError.__module__.startswith(
        "ai_studio_agent_builder.application"
    )


def test_legacy_flat_imports_reference_packaged_contracts() -> None:
    assert issubclass(
        legacy_interaction.AIInteractionService,
        interaction_facade.AIInteractionService,
    )
    assert builder_service.BuilderConversationService.__module__.startswith(
        "ai_studio_agent_builder.application"
    )
    assert preview_service.AgentPreviewService.__module__.startswith(
        "ai_studio_agent_builder.application"
    )
    assert file_lifecycle.ConversationFileService.__module__.startswith(
        "ai_studio_agent_builder.application"
    )
    assert builder_run.BuilderRunPort.__module__.startswith(
        "ai_studio_agent_builder.application"
    )
    assert connection_port.ConnectionValidator.__module__.startswith(
        "ai_studio_agent_builder.application"
    )
    assert conversation_storage.AttachmentStore.__module__.startswith(
        "ai_studio_agent_builder.application"
    )
    assert run_adapter.BuilderAgentsRunAdapter.__module__.startswith(
        "ai_studio_agent_builder.builder"
    )
    assert local_attachments.LocalAttachmentStore.__module__.startswith(
        "ai_studio_agent_builder.infrastructure"
    )
    assert provider_connection.YandexConnectionValidator.__module__.startswith(
        "ai_studio_agent_builder.infrastructure"
    )
    assert issubclass(
        legacy_bot_handlers.TelegramHandlers,
        telegram_handlers.TelegramHandlers,
    )
    assert (
        legacy_bot_utils.sanitize_download_filename
        is telegram_media.sanitize_download_filename
    )
    assert legacy_messages.MessageService is telegram_messages.MessageService
    assert (
        legacy_telegram_flow.PerUserRequestGate
        is telegram_request_gate.PerUserRequestGate
    )
    assert (
        legacy_telegram_session.HttpProxyTelegramSession
        is telegram_http_session.HttpProxyTelegramSession
    )
    assert legacy_base_agent.CustomAgent is base_agent.CustomAgent
    assert (
        legacy_coordinator_agent.build_coordinator_agent
        is coordinator_agent.build_coordinator_agent
    )
    assert (
        legacy_one_prompt_agent.build_one_prompt_agent
        is one_prompt_agent.build_one_prompt_agent
    )
    assert legacy_rag_agent.build_rag_agent is rag_agent.build_rag_agent
    assert (
        legacy_specification_tools.update_agent_specification
        is specification_tools.update_agent_specification
    )
    assert legacy_delegate_tools.delegate_rag is delegate_tools.delegate_rag
    assert legacy_finish_dialog.finish_dialog is finish_dialog.finish_dialog
    assert legacy_vector_index.create_search_index is vector_index.create_search_index
    assert config.AIServiceConfig is settings.AIServiceConfig
    assert config.AgentRuntimeConfig is settings.AgentRuntimeConfig
    assert config.ApiKeyStoreConfig is settings.ApiKeyStoreConfig
    assert config.AppConfig is settings.AppConfig
    assert config.BotConfig is settings.BotConfig
    assert config.ConnectionConfig is settings.ConnectionConfig
    assert config.ModelConfig is settings.ModelConfig
    assert config.PathConfig is settings.PathConfig
    assert config.SessionDBConfig is settings.SessionDBConfig
    assert config.WebUIConfig is settings.WebUIConfig
    assert legacy_interaction.Attachment is interaction.Attachment
    assert legacy_interaction.InteractionRequest is interaction.InteractionRequest
    assert legacy_interaction.InteractionResult is interaction.InteractionResult
    assert legacy_interaction.AgentTestRequest is interaction.AgentTestRequest
    assert legacy_interaction.AgentTestResult is interaction.AgentTestResult
    assert legacy_interaction.UploadValidationError is interaction.UploadValidationError
    assert (
        legacy_agent_test_panel.AgentSpecificationActions
        is agent_test_panel.AgentSpecificationActions
    )
    assert legacy_attachments.preview_kind_for_mime is attachments.preview_kind_for_mime
    assert legacy_chat_flow.build_user_content is chat_flow.build_user_content
    assert (
        legacy_connection.credentials_from_connection
        is connection.credentials_from_connection
    )
    assert (
        legacy_developer_bundle.build_developer_bundle
        is developer_bundle.build_developer_bundle
    )
    assert (
        legacy_result_view.agent_specification_json
        is result_view.agent_specification_json
    )
    assert legacy_uploads.attachment_record is uploads.attachment_record
    assert (
        legacy_user_guidance.render_next_steps_sidebar
        is user_guidance.render_next_steps_sidebar
    )
    assert legacy_logging.ContextFormatter is observability.ContextFormatter
    assert legacy_logging.bind_logger is observability.bind_logger
    assert legacy_logging.build_formatter is observability.build_formatter
    assert (
        legacy_logging.configure_console_logging
        is observability.configure_console_logging
    )
    assert legacy_logging.configure_logging is observability.configure_logging
    assert legacy_agent_sessions.get_session is agent_sessions.get_session
    assert legacy_user_store.UserStore is telegram_user_store.UserStore
    assert legacy_user_store.UserSecrets is telegram_user_store.UserSecrets
    assert legacy_api_key_store.ApiKeyConnection is api_key_port.ApiKeyConnection
    assert legacy_api_key_store.ApiKeyStoreError is api_key_port.ApiKeyStoreError
    assert api_key_store.ApiKeyConnection is api_key_port.ApiKeyConnection
    assert api_key_store.ApiKeyStoreError is api_key_port.ApiKeyStoreError
    assert (
        legacy_api_key_store.EncryptedApiKeyStore is api_key_store.EncryptedApiKeyStore
    )
    assert (
        legacy_specification.InvalidSpecificationRootError
        is specification_codec.InvalidSpecificationRootError
    )
    assert (
        legacy_specification.loads_agent_specification
        is specification_codec.loads_agent_specification
    )
    assert (
        legacy_result_assembly.AgentRunCollector is sdk_event_adapter.AgentRunCollector
    )
    assert legacy_result_assembly.AgentRunResult is result_assembly.AgentRunResult
    assert legacy_result_assembly.ResultAssembler is result_assembly.ResultAssembler
    assert legacy_request_context.RequestContext is builder_context.RequestContext
    assert legacy_config.AgentRuntimeConfig is config.AgentRuntimeConfig
    assert legacy_config.AIServiceConfig is config.AIServiceConfig
    assert legacy_config.ConnectionConfig is config.ConnectionConfig
    assert legacy_config.ModelConfig is config.ModelConfig
    assert legacy_config.load_config is config.load_config
    assert legacy_config.load_web_ui_config is config.load_web_ui_config
    assert legacy_builder_state.ConversationState is builder_state.ConversationState
    assert legacy_builder_state.ConversationOptions is builder_state.ConversationOptions
    assert legacy_file_security.sanitize_filename is file_policy.sanitize_filename
    assert legacy_upload_files.resolve_upload_path is file_policy.resolve_upload_path
    assert legacy_upload_files.upload_local_file is files_gateway.upload_local_file
    assert legacy_credentials.AIStudioCredentials is dto.AIStudioCredentials
    assert legacy_credentials.UserCredentials is dto.UserCredentials
    assert legacy_credentials.get_api_key_client is client_factory.get_api_key_client
    assert (
        legacy_credentials.get_async_api_key_client
        is client_factory.get_async_api_key_client
    )
    assert legacy_agent_runner.AgentRunPreview is agent_runner.AgentRunPreview
    assert legacy_agent_runner.AgentRunnerError is agent_runner.AgentRunnerError
    assert legacy_runtime.ExecutableAgentConfig is runtime.ExecutableAgentConfig
    assert (
        legacy_runtime.compile_agent_specification
        is runtime.compile_agent_specification
    )
    assert legacy_specification.AgentSpecification is specification.AgentSpecification
    assert legacy_specification.KnowledgeSource is specification.KnowledgeSource
    assert legacy_catalog.TemplateId is catalog.TemplateId
    assert legacy_routing.ConversationOptions is routing.ConversationOptions
    assert legacy_routing.resolve_explicit_route is routing.resolve_explicit_route
    assert (
        legacy_yandex_runner.YandexResponsesAgentRunner
        is responses_runner.YandexResponsesAgentRunner
    )
