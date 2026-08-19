from ai_studio_agent_builder.composition import build_telegram_app
from ai_studio_agent_builder.entrypoints.telegram import main as packaged_telegram_main
from ai_studio_agent_builder.entrypoints.web import main as packaged_web_ui_main
from ai_studio_agent_builder.experimental.oauth.app import create_gateway_app


def test_runtime_entrypoints_remain_importable() -> None:
    assert callable(build_telegram_app)
    assert callable(create_gateway_app)
    assert callable(packaged_telegram_main)
    assert callable(packaged_web_ui_main)
