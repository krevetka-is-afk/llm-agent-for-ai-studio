import agent_runtime as legacy_runtime
import agent_specification as legacy_specification
import component_catalog as legacy_catalog

import ai_studio_agent_builder as public_api
from ai_studio_agent_builder.domain import catalog, runtime, specification


def test_public_api_reexports_stable_domain_contracts() -> None:
    assert public_api.AgentSpecification is specification.AgentSpecification
    assert public_api.AgentSpecificationStatus is specification.AgentSpecificationStatus
    assert public_api.ExecutableAgentConfig is runtime.ExecutableAgentConfig
    assert public_api.KnowledgeSource is specification.KnowledgeSource
    assert public_api.TemplateId is catalog.TemplateId
    assert public_api.ToolDescriptor is specification.ToolDescriptor
    assert public_api.compile_agent_specification is runtime.compile_agent_specification


def test_legacy_flat_imports_reference_packaged_contracts() -> None:
    assert legacy_runtime.ExecutableAgentConfig is runtime.ExecutableAgentConfig
    assert (
        legacy_runtime.compile_agent_specification
        is runtime.compile_agent_specification
    )
    assert legacy_specification.AgentSpecification is specification.AgentSpecification
    assert legacy_specification.KnowledgeSource is specification.KnowledgeSource
    assert legacy_catalog.TemplateId is catalog.TemplateId
