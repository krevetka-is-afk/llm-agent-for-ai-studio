from pathlib import Path
from typing import Any, cast

import yaml


REPOSITORY_ROOT = Path(__file__).parents[1]
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "release-readiness.yml"
YANDEX_E2E_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "yandex-e2e.yml"
GITLEAKS_IGNORE = REPOSITORY_ROOT / ".gitleaksignore"
EXPECTED_GITLEAKS_FALSE_POSITIVES = {
    "70af94b04a5af6e88223427790bb754e2db23f4e:tests/test_yc_connect.py:generic-api-key:120",
    "70af94b04a5af6e88223427790bb754e2db23f4e:tests/test_yc_connect.py:generic-api-key:129",
    "70af94b04a5af6e88223427790bb754e2db23f4e:tests/test_yc_connect.py:generic-api-key:163",
    "70af94b04a5af6e88223427790bb754e2db23f4e:tests/test_yc_connect.py:generic-api-key:182",
}


def _workflow(path: Path = YANDEX_E2E_WORKFLOW) -> dict[str | bool, Any]:
    return cast(
        dict[str | bool, Any],
        yaml.safe_load(path.read_text(encoding="utf-8")),
    )


def test_credentialed_workflow_is_manual_and_read_only() -> None:
    workflow = _workflow()
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_credentialed_jobs_use_dedicated_environment_and_cleanup() -> None:
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


def test_release_secret_scan_is_manual_and_checks_reachable_history() -> None:
    workflow = _workflow(RELEASE_WORKFLOW)
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {"workflow_dispatch"}
    assert workflow["permissions"] == {"contents": "read"}

    steps = workflow["jobs"]["secret-history"]["steps"]
    assert steps[0]["with"]["fetch-depth"] == 0
    assert steps[1]["uses"].startswith("gitleaks/gitleaks-action@")
    assert steps[1]["env"]["GITLEAKS_ENABLE_COMMENTS"] == "false"


def test_change_secret_scan_has_the_history_required_for_commit_ranges() -> None:
    steps = _workflow(CI_WORKFLOW)["jobs"]["secret-scan"]["steps"]

    assert steps[0]["with"]["fetch-depth"] == 0
    assert steps[1]["uses"].startswith("gitleaks/gitleaks-action@")
    assert steps[1]["env"]["GITLEAKS_ENABLE_COMMENTS"] == "false"


def test_gitleaks_allowlist_is_limited_to_reviewed_test_fingerprints() -> None:
    fingerprints = {
        line
        for line in GITLEAKS_IGNORE.read_text(encoding="utf-8").splitlines()
        if line
    }

    assert fingerprints == EXPECTED_GITLEAKS_FALSE_POSITIVES
