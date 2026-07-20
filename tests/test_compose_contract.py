from pathlib import Path
from typing import Any, cast

import yaml


REPOSITORY_ROOT = Path(__file__).parents[1]


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
        "ui/app.py",
    ]
    assert services["telegram-bot"]["command"] == ["python", "app.py"]
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


def test_dockerfile_keeps_flat_runtime_contract() -> None:
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ENV PYTHONPATH=/app" in dockerfile
    assert "COPY --chown=app:app src/ ." in dockerfile


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
