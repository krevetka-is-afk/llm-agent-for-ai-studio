import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
PACKAGE_ROOT = "ai_studio_agent_builder/"
REQUIRED_PACKAGE_FILES = {
    f"{PACKAGE_ROOT}__init__.py",
    f"{PACKAGE_ROOT}application/interaction_facade.py",
    f"{PACKAGE_ROOT}entrypoints/telegram.py",
    f"{PACKAGE_ROOT}entrypoints/web.py",
    f"{PACKAGE_ROOT}experimental/oauth/app.py",
}
LEGACY_WHEEL_PATHS = {
    "ai_interaction_service.py",
    "app.py",
    "custom_agents/",
    "ui/",
}


def _build_distribution(output_dir: Path) -> tuple[Path, Path]:
    subprocess.run(
        [
            "uv",
            "build",
            "--wheel",
            "--sdist",
            "--out-dir",
            str(output_dir),
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(output_dir.glob("*.whl"))
    source_distribution = next(output_dir.glob("*.tar.gz"))
    return wheel, source_distribution


def test_distribution_contains_the_package_and_imports_without_checkout(
    tmp_path: Path,
) -> None:
    wheel, source_distribution = _build_distribution(tmp_path / "dist")

    with zipfile.ZipFile(wheel) as archive:
        wheel_files = set(archive.namelist())
    assert REQUIRED_PACKAGE_FILES <= wheel_files
    assert not any(
        path == legacy_path or path.startswith(legacy_path)
        for path in wheel_files
        for legacy_path in LEGACY_WHEEL_PATHS
    )

    with tarfile.open(source_distribution, mode="r:gz") as archive:
        source_files = {
            member.name.split("/", maxsplit=1)[-1] for member in archive.getmembers()
        }
    assert {
        f"src/{package_file}" for package_file in REQUIRED_PACKAGE_FILES
    } <= source_files

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(wheel)!r}); "
                "import ai_studio_agent_builder; "
                "from ai_studio_agent_builder.application.interaction_facade "
                "import AIInteractionService; "
                "from ai_studio_agent_builder.entrypoints.telegram import main; "
                "from ai_studio_agent_builder.experimental.oauth.app "
                "import create_gateway_app; "
                "assert ai_studio_agent_builder.AgentSpecification; "
                "assert AIInteractionService; "
                "assert callable(create_gateway_app); "
                "assert callable(main)"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
