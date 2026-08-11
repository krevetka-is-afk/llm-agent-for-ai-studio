"""Composition root for concrete runtime services and adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .application.builder_service import BuilderConversationService
from .application.dto import AIStudioCredentials
from .application.file_lifecycle import (
    ConversationFileService,
    PreviewInputFileLifecycle,
)
from .application.interaction_facade import (
    AIInteractionComponents,
    AIInteractionService,
)
from .application.ports.agent_runner import AgentRunner, AgentRunnerFactory
from .application.ports.builder_run import BuilderRunPort
from .application.ports.connection import ConnectionValidator
from .application.ports.conversation_storage import (
    AttachmentStore,
    ConversationSessionStore,
)
from .application.ports.file_resource_gateway import FileResourceGatewayFactory
from .application.preview_service import AgentPreviewService
from .application.settings import AIServiceConfig, AppConfig
from .builder.agents.coordinator_agent import build_coordinator_agent
from .builder.agents.one_prompt_agent import build_one_prompt_agent
from .builder.agents.rag_agent import build_rag_agent
from .builder.agents.run_adapter import BuilderAgentsRunAdapter
from .config import load_config, load_web_ui_config
from .infrastructure.observability.logging import configure_console_logging
from .infrastructure.persistence.agent_sessions import (
    SQLiteConversationSessionStore,
    get_session,
)
from .infrastructure.persistence.api_key_store import EncryptedApiKeyStore
from .infrastructure.persistence.local_attachments import LocalAttachmentStore
from .infrastructure.persistence.telegram_user_store import UserStore
from .infrastructure.yandex_ai_studio.client_factory import (
    get_api_key_client,
    get_async_api_key_client,
)
from .infrastructure.yandex_ai_studio.connection import YandexConnectionValidator
from .infrastructure.yandex_ai_studio.files_gateway import (
    YandexFileResourceGatewayFactory,
    upload_local_file,
)
from .infrastructure.yandex_ai_studio.responses_runner import (
    YandexAgentRunnerFactory,
)
from .presentation.telegram.handlers import create_router as create_telegram_router
from .presentation.telegram.http_session import HttpProxyTelegramSession


ClientFactory = Callable[[AIStudioCredentials], Any]
FileUploader = Callable[[Any, Path, str], str]
LegacyAgentRunnerFactory = Callable[[Any, str], AgentRunner]


@dataclass(frozen=True)
class WebServices:
    """Concrete services required by the supported Streamlit runtime."""

    api_key_store: EncryptedApiKeyStore
    ai_interaction: AIInteractionService


@dataclass(frozen=True)
class TelegramRuntime:
    bot: Bot
    dispatcher: Dispatcher


def build_web_services() -> WebServices:
    """Build the Streamlit dependency graph from validated configuration."""

    config = load_web_ui_config()
    return WebServices(
        api_key_store=EncryptedApiKeyStore(
            config.api_key_store.storage_path,
            config.api_key_store.encryption_key,
        ),
        ai_interaction=build_ai_interaction_service(config.ai_service),
    )


def build_ai_interaction_service(
    config: AIServiceConfig,
    *,
    rag_agent: Any | None = None,
    one_prompt_agent: Any | None = None,
    coordinator_agent: Any | None = None,
    agent_runner_factory: LegacyAgentRunnerFactory | None = None,
    builder_run_port: BuilderRunPort | None = None,
    connection_validator: ConnectionValidator | None = None,
    generated_agent_runner_factory: AgentRunnerFactory | None = None,
    file_resource_gateway_factory: FileResourceGatewayFactory | None = None,
    attachment_store: AttachmentStore | None = None,
    conversation_session_store: ConversationSessionStore | None = None,
    sync_client_factory: ClientFactory | None = None,
    async_client_factory: ClientFactory | None = None,
    file_uploader: FileUploader | None = None,
) -> AIInteractionService:
    return AIInteractionService(
        build_ai_interaction_components(
            config,
            rag_agent=rag_agent,
            one_prompt_agent=one_prompt_agent,
            coordinator_agent=coordinator_agent,
            agent_runner_factory=agent_runner_factory,
            builder_run_port=builder_run_port,
            connection_validator=connection_validator,
            generated_agent_runner_factory=generated_agent_runner_factory,
            file_resource_gateway_factory=file_resource_gateway_factory,
            attachment_store=attachment_store,
            conversation_session_store=conversation_session_store,
            sync_client_factory=sync_client_factory,
            async_client_factory=async_client_factory,
            file_uploader=file_uploader,
        ),
    )


def build_ai_interaction_components(
    config: AIServiceConfig,
    *,
    rag_agent: Any | None = None,
    one_prompt_agent: Any | None = None,
    coordinator_agent: Any | None = None,
    agent_runner_factory: LegacyAgentRunnerFactory | None = None,
    builder_run_port: BuilderRunPort | None = None,
    connection_validator: ConnectionValidator | None = None,
    generated_agent_runner_factory: AgentRunnerFactory | None = None,
    file_resource_gateway_factory: FileResourceGatewayFactory | None = None,
    attachment_store: AttachmentStore | None = None,
    conversation_session_store: ConversationSessionStore | None = None,
    sync_client_factory: ClientFactory | None = None,
    async_client_factory: ClientFactory | None = None,
    file_uploader: FileUploader | None = None,
) -> AIInteractionComponents:
    sync_client_factory = sync_client_factory or (
        lambda credentials: get_api_key_client(credentials, config.connection)
    )
    async_client_factory = async_client_factory or (
        lambda credentials: get_async_api_key_client(credentials, config.connection)
    )
    file_uploader = file_uploader or upload_local_file

    if builder_run_port is None:
        builder_run_port = BuilderAgentsRunAdapter(
            rag_agent=rag_agent or build_rag_agent(config.rag_model, get_session),
            one_prompt_agent=one_prompt_agent
            or build_one_prompt_agent(config.one_prompt, get_session),
            coordinator_agent=coordinator_agent
            or build_coordinator_agent(config.consultant, get_session),
            sync_client_factory=sync_client_factory,
            async_client_factory=async_client_factory,
            file_uploader=file_uploader,
        )

    connection_validator = connection_validator or YandexConnectionValidator(
        sync_client_factory,
        model_name=config.one_prompt.model_name,
    )
    generated_agent_runner_factory = (
        generated_agent_runner_factory
        or YandexAgentRunnerFactory(
            sync_client_factory,
            runner_builder=agent_runner_factory,
        )
    )
    attachment_store = attachment_store or LocalAttachmentStore(
        config.paths.uploaded_files_dir
    )
    file_resource_gateway_factory = (
        file_resource_gateway_factory
        or YandexFileResourceGatewayFactory(sync_client_factory)
    )
    conversation_session_store = (
        conversation_session_store
        or SQLiteConversationSessionStore(
            {
                config.rag_model.sessions_db_path,
                config.one_prompt.sessions_db_path,
                config.consultant.sessions_db_path,
            }
        )
    )
    return AIInteractionComponents(
        builder=BuilderConversationService(builder_run_port, attachment_store),
        preview=AgentPreviewService(
            config.generated_agent_runtime,
            generated_agent_runner_factory,
            PreviewInputFileLifecycle(
                attachment_store,
                file_resource_gateway_factory,
            ),
        ),
        files=ConversationFileService(
            attachment_store,
            conversation_session_store,
        ),
        connection_validator=connection_validator,
    )


def build_telegram_app(config: AppConfig) -> tuple[Bot, Dispatcher]:
    session = (
        HttpProxyTelegramSession(config.bot.telegram_proxy_url)
        if config.bot.telegram_proxy_url is not None
        else None
    )
    bot = Bot(
        token=config.bot.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    dispatcher = Dispatcher()
    router = create_telegram_router(
        bot,
        build_ai_interaction_service(config.ai_service),
        UserStore(),
    )
    dispatcher.include_router(router)
    return bot, dispatcher


def build_telegram_runtime() -> TelegramRuntime:
    bot, dispatcher = build_telegram_app(load_config())
    return TelegramRuntime(bot=bot, dispatcher=dispatcher)


def configure_web_logging() -> None:
    """Configure logging for the executable web runtime."""

    configure_console_logging()


def configure_telegram_logging() -> None:
    configure_console_logging()


__all__ = [
    "WebServices",
    "TelegramRuntime",
    "build_ai_interaction_components",
    "build_ai_interaction_service",
    "build_web_services",
    "build_telegram_app",
    "build_telegram_runtime",
    "configure_telegram_logging",
    "configure_web_logging",
]
