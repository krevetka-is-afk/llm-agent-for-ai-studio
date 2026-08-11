from pathlib import Path
from typing import Any, cast

import yaml


REPOSITORY_ROOT = Path(__file__).parents[1]
YANDEX_E2E_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "yandex-e2e.yml"


def _workflow() -> dict[str | bool, Any]:
    return cast(
        dict[str | bool, Any],
        yaml.safe_load(YANDEX_E2E_WORKFLOW.read_text(encoding="utf-8")),
    )


def test_credentialed_workflow_is_manual_and_read_only() -> None:
    workflow = _workflow()
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_credentialed_jobs_require_protected_environment_and_cleanup() -> None:
    jobs = _workflow()["jobs"]

    assert set(jobs) == {"core", "web-search"}
    for job in jobs.values():
        assert job["environment"] == "yandex-ai-studio-e2e"
        assert job["env"]["RUN_YANDEX_AI_STUDIO_E2E"] == "1"
        assert job["env"]["YC_AI_STUDIO_E2E_KEEP_REMOTE"] == "0"
        assert "secrets.YC_AI_STUDIO_API_KEY" in job["env"]["YC_AI_STUDIO_API_KEY"]
        assert "secrets.YC_AI_STUDIO_FOLDER_ID" in job["env"]["YC_AI_STUDIO_FOLDER_ID"]

    core_command = jobs["core"]["steps"][-1]["run"]
    assert "not yandex_ai_studio_web_search_e2e" in core_command
    assert "tests/e2e" in core_command
    assert "inputs.include_web_search" in jobs["web-search"]["if"]
    assert jobs["web-search"]["needs"] == "core"
