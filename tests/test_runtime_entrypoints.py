from app import create_app
from ai_studio_agent_builder.entrypoints.web import main as packaged_web_ui_main
from experimental.oauth.app import create_gateway_app
from ui.app import main as web_ui_main


def test_runtime_entrypoints_remain_importable() -> None:
    assert callable(create_app)
    assert callable(create_gateway_app)
    assert callable(web_ui_main)
    assert web_ui_main is packaged_web_ui_main
