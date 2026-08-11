from pathlib import Path
from typing import Any, cast

import yaml


REPOSITORY_ROOT = Path(__file__).parents[1]
WEB_RUNTIME_PATHS = {
    "YC_API_KEY_DB_PATH": ".local/api_keys.db",
    "UPLOADED_FILES_DIR": ".local/uploaded_files",
    "CONVERSATION_DB_PATH": ".local/conversation.db",
}


def _compose_services() -> dict[str, dict[str, Any]]:
    document = yaml.safe_load(
        (REPOSITORY_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )
    return cast(dict[str, dict[str, Any]], document["services"])


def test_compose_keeps_mvp_entrypoints_and_experimental_profiles() -> None:
    services = _compose_services()

    assert services["web-ui"]["command"][:3] == [
        "streamlit",
        "run",
        "src/ai_studio_agent_builder/entrypoints/web.py",
    ]
    assert services["telegram-bot"]["command"] == [
        "python",
        "-m",
        "ai_studio_agent_builder.entrypoints.telegram",
    ]
    assert services["oauth-gateway"]["command"] == [
        "python",
        "-m",
        "experimental.oauth.app",
    ]
    assert services["telegram-bot"]["profiles"] == ["telegram-experimental"]
    assert services["oauth-gateway"]["profiles"] == ["oauth-experimental"]


def test_compose_services_keep_runtime_limits() -> None:
    for service in _compose_services().values():
        assert service["mem_limit"] == "1g"
        assert service["pids_limit"] == 256
        assert service["security_opt"] == ["no-new-privileges:true"]
        assert service["cap_drop"] == ["ALL"]
        assert service["read_only"] is True
        assert service["init"] is True
        assert service["tmpfs"] == ["/tmp:size=64m,mode=1777"]


def test_web_env_example_uses_project_local_runtime_paths() -> None:
    values = {
        name: value
        for line in (REPOSITORY_ROOT / ".env.web.example")
        .read_text(encoding="utf-8")
        .splitlines()
        if line and not line.startswith("#")
        for name, value in [line.split("=", maxsplit=1)]
    }

    for name, expected_path in WEB_RUNTIME_PATHS.items():
        assert values[name] == expected_path
        assert not Path(values[name]).is_absolute()


def test_compose_overrides_web_runtime_paths_with_data_volume() -> None:
    web_environment = _compose_services()["web-ui"]["environment"]

    assert web_environment == {
        name: f"/data/{Path(local_path).name}"
        for name, local_path in WEB_RUNTIME_PATHS.items()
    }


def test_dockerfile_installs_and_runs_the_package() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ENV PYTHONPATH" not in dockerfile
    assert "uv sync --locked --no-install-project" in dockerfile
    assert "uv sync --locked --no-editable" in dockerfile
    assert "COPY src/ai_studio_agent_builder src/ai_studio_agent_builder" in dockerfile
    assert "COPY --chown=app:app src/ ." not in dockerfile


def test_docker_build_context_excludes_credentials_and_local_agent_state() -> None:
    patterns = {
        line.strip()
        for line in (REPOSITORY_ROOT / ".dockerignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert "authorized_key.json" in patterns
    assert "*credentials*.json" in patterns
    assert ".omx" in patterns
    assert "graphify-out/" in patterns
