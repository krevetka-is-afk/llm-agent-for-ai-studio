from app import create_app
from experimental.oauth.app import create_gateway_app
from ui.app import main as web_ui_main


def test_runtime_entrypoints_remain_importable() -> None:
    assert callable(create_app)
    assert callable(create_gateway_app)
    assert callable(web_ui_main)
