import agent_runner as legacy_agent_runner
import agent_runtime as legacy_runtime
import agent_specification as legacy_specification
import component_catalog as legacy_catalog
import conversation_state as legacy_builder_state
import credentials as legacy_credentials
import custom_agents.tools.upload_files as legacy_upload_files
import file_security as legacy_file_security
import routing as legacy_routing
import yandex_responses_runner as legacy_yandex_runner

import ai_studio_agent_builder as public_api
from ai_studio_agent_builder.application import builder_state, dto, file_policy
from ai_studio_agent_builder.application.ports import agent_runner
from ai_studio_agent_builder.domain import catalog, routing, runtime, specification
from ai_studio_agent_builder.infrastructure.yandex_ai_studio import (
    client_factory,
    files_gateway,
    responses_runner,
)


def test_public_api_reexports_stable_domain_contracts() -> None:
    assert public_api.AgentSpecification is specification.AgentSpecification
    assert public_api.AgentSpecificationStatus is specification.AgentSpecificationStatus
    assert public_api.ExecutableAgentConfig is runtime.ExecutableAgentConfig
    assert public_api.KnowledgeSource is specification.KnowledgeSource
    assert public_api.TemplateId is catalog.TemplateId
    assert public_api.ToolDescriptor is specification.ToolDescriptor
    assert public_api.compile_agent_specification is runtime.compile_agent_specification


def test_legacy_flat_imports_reference_packaged_contracts() -> None:
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
