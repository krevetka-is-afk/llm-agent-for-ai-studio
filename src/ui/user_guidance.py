import json
from collections.abc import Mapping, Sequence
from typing import Any

import streamlit as st

from ui.developer_bundle import build_developer_bundle


AI_STUDIO_URL = "https://aistudio.yandex.ru/"
CREATE_AGENT_GUIDE_URL = (
    "https://aistudio.yandex.ru/docs/ru/ai-studio/operations/agents/"
    "create-agent-ui.html"
)
AI_AGENTS_GUIDE_URL = "https://aistudio.yandex.ru/docs/ru/ai-studio/concepts/agents/"

MODEL_HELP = (
    "Модель Yandex AI Studio, на которой был выполнен тестовый запрос. "
    "Выберите эту же модель при ручном создании агента."
)
INSTRUCTIONS_HELP = (
    "Системная инструкция определяет роль, правила и ожидаемый формат ответа "
    "агента. Скопируйте её целиком в поле инструкции Agent Atelier."
)
TOOLS_HELP = (
    "Инструменты дают агенту дополнительные возможности: Web Search ищет "
    "актуальные сведения в интернете, File Search отвечает по вашим файлам."
)
GENERATION_SETTINGS_HELP = (
    "Temperature управляет вариативностью ответа, а максимальное число токенов "
    "ограничивает его длину."
)


def render_next_steps_sidebar() -> None:
    with st.sidebar:
        st.divider()
        st.subheader(
            "После создания",
            help=(
                "Agent Builder подготавливает и проверяет настройки. После этого "
                "агента можно сохранить вручную в Agent Atelier или передать "
                "разработчику для подключения к приложению."
            ),
        )
        with st.expander("Куда идти с результатом?", expanded=True):
            st.markdown(
                """
1. **Проверьте здесь:** задайте несколько вопросов и проверьте источники.
2. **Сохраните в AI Studio:** создайте агента в Agent Atelier и перенесите
   настройки из готовой карточки.
3. **Для сайта или бота:** скачайте пакет из карточки и передайте разработчику.
"""
            )
            st.link_button(
                "Открыть AI Studio",
                AI_STUDIO_URL,
                help="Открывает интерфейс AI Studio в новой вкладке.",
                type="primary",
                width="stretch",
            )
            st.markdown(
                f"[Пошаговое создание агента]({CREATE_AGENT_GUIDE_URL}) · "
                f"[Что такое AI-агенты]({AI_AGENTS_GUIDE_URL})"
            )


def render_agent_next_steps(
    specification: Mapping[str, Any],
    runtime_json: str,
    *,
    key_prefix: str,
) -> None:
    runtime = _runtime_record(runtime_json)

    st.markdown("#### Агент проверен. Что делать дальше?")
    st.success(
        "Для работы без программирования сохраните настройки как постоянного "
        "агента в Yandex AI Studio."
    )
    st.markdown(
        """
1. Откройте **Agent Atelier → Агенты**.
2. Нажмите **Создать агента**.
3. Перенесите настройки из раздела ниже.
4. Проверьте агента в AI Studio и нажмите **Создать**.
"""
    )
    st.link_button(
        "Создать агента в AI Studio",
        AI_STUDIO_URL,
        key=f"{key_prefix}-open-agent-atelier",
        help=(
            "Открывает AI Studio. Автоматический импорт JSON пока не "
            "поддерживается, поэтому настройки нужно перенести вручную."
        ),
        type="primary",
    )
    st.markdown(f"[Официальная пошаговая инструкция]({CREATE_AGENT_GUIDE_URL})")

    with st.expander("Настройки для переноса в AI Studio", expanded=False):
        st.markdown("**Модель**", help=MODEL_HELP)
        st.code(_string_value(runtime.get("model_name")), language=None)

        st.markdown("**Инструкция агента**", help=INSTRUCTIONS_HELP)
        st.code(_string_value(runtime.get("instructions")), language=None)

        st.markdown("**Инструменты**", help=TOOLS_HELP)
        tool_descriptions = _tool_descriptions(runtime.get("tools"))
        if tool_descriptions:
            for description in tool_descriptions:
                st.markdown(f"- {description}")
        else:
            st.caption("Дополнительные инструменты не требуются.")

        st.markdown("**Настройки генерации**", help=GENERATION_SETTINGS_HELP)
        st.markdown(
            f"- Temperature: `{runtime.get('temperature', 'не указана')}`\n"
            "- Максимум токенов ответа: "
            f"`{runtime.get('max_output_tokens', 'не указан')}`"
        )

    st.markdown("**Нужно подключить агента к сайту, боту или внутренней системе?**")
    st.caption(
        "Скачайте технический пакет и передайте его разработчику. "
        "Программировать самостоятельно не требуется."
    )
    st.download_button(
        "Скачать пакет для разработчика (.zip)",
        data=build_developer_bundle(specification, runtime_json),
        file_name="generated-agent.zip",
        mime="application/zip",
        key=f"{key_prefix}-developer-bundle-download",
        help=(
            "Архив содержит спецификацию, проверенную runtime-конфигурацию, "
            "пример запуска, шаблон переменных окружения и README. Секретов "
            "в архиве нет."
        ),
    )


def _runtime_record(runtime_json: str) -> Mapping[str, Any]:
    value = json.loads(runtime_json)
    if not isinstance(value, Mapping):
        raise ValueError("Runtime config must be a JSON object")
    return value


def _tool_descriptions(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        str | bytes | bytearray,
    ):
        return ()
    descriptions: list[str] = []
    for tool in value:
        if not isinstance(tool, Mapping):
            continue
        tool_type = tool.get("type")
        if tool_type == "web_search":
            context_size = tool.get("search_context_size", "medium")
            descriptions.append(
                f"**Web Search** — поиск в интернете, контекст `{context_size}`."
            )
        elif tool_type == "file_search":
            vector_store_ids = tool.get("vector_store_ids")
            index_id = (
                vector_store_ids[0]
                if isinstance(vector_store_ids, list) and vector_store_ids
                else "не указан"
            )
            descriptions.append(
                f"**File Search** — поиск по файлам, ID индекса `{index_id}`."
            )
    return tuple(descriptions)


def _string_value(value: Any) -> str:
    return value if isinstance(value, str) and value else "не указано"
