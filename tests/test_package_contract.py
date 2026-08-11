from pathlib import Path

import ai_studio_agent_builder as public_api
from ai_studio_agent_builder import config
from ai_studio_agent_builder.application import errors, settings
from ai_studio_agent_builder.domain import (
    catalog,
    runtime,
    specification,
    specification_codec,
)


REPOSITORY_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"


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


def test_configuration_types_have_one_authoritative_definition() -> None:
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


def test_source_tree_contains_only_the_installable_package() -> None:
    assert list(SOURCE_ROOT.glob("*.py")) == []
    assert list((SOURCE_ROOT / "custom_agents").glob("**/*.py")) == []
    assert list((SOURCE_ROOT / "ui").glob("**/*.py")) == []
