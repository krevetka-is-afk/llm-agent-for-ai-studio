from __future__ import annotations

import ast
from collections import defaultdict
from importlib.util import resolve_name
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "ai_studio_agent_builder"
LAYER_IMPORTS = {
    "domain": frozenset({"domain"}),
    "application": frozenset({"domain", "application"}),
    "builder": frozenset({"domain", "application", "builder"}),
    "infrastructure": frozenset({"domain", "application", "infrastructure"}),
    "presentation": frozenset({"domain", "application", "presentation"}),
    "entrypoints": frozenset({"composition", "presentation", "entrypoints"}),
}
PROVIDER_MODULES = frozenset({"agents", "openai"})
PRESENTATION_MODULES = frozenset({"aiogram", "streamlit"})


def test_package_respects_layer_boundaries_and_has_no_import_cycles() -> None:
    assert _architecture_violations(PACKAGE_ROOT) == []


def test_checker_rejects_forbidden_layer_import(tmp_path: Path) -> None:
    package_root = tmp_path / "example"
    _write_module(package_root / "domain" / "model.py", "import example.infrastructure")
    _write_module(package_root / "infrastructure" / "__init__.py", "")

    violations = _architecture_violations(package_root)

    assert any("domain cannot import infrastructure" in item for item in violations)


def test_checker_rejects_package_import_cycle(tmp_path: Path) -> None:
    package_root = tmp_path / "example"
    _write_module(package_root / "domain" / "a.py", "from . import b")
    _write_module(package_root / "domain" / "b.py", "from . import a")

    violations = _architecture_violations(package_root)

    assert any("import cycle:" in item for item in violations)


def _architecture_violations(package_root: Path) -> list[str]:
    module_paths = {
        _module_name(path, package_root): path for path in package_root.rglob("*.py")
    }
    known_modules = frozenset(module_paths)
    graph: dict[str, set[str]] = defaultdict(set)
    violations: list[str] = []

    for source_module, path in sorted(module_paths.items()):
        source_layer = _layer_of(source_module, package_root.name)
        for imported_module in _imports(path, source_module, known_modules):
            if imported_module in known_modules:
                graph[source_module].add(imported_module)
                target_layer = _layer_of(imported_module, package_root.name)
                if source_layer in LAYER_IMPORTS and (
                    target_layer not in LAYER_IMPORTS[source_layer]
                ):
                    violations.append(
                        f"{source_module}: {source_layer} cannot import "
                        f"{target_layer or 'package root'} ({imported_module})"
                    )
                continue

            top_level = imported_module.partition(".")[0]
            if source_layer == "domain" and not _is_stdlib(top_level):
                violations.append(
                    f"{source_module}: domain cannot import external module {top_level}"
                )
            if source_layer == "application" and top_level in (
                PROVIDER_MODULES | PRESENTATION_MODULES
            ):
                violations.append(
                    f"{source_module}: application cannot import adapter SDK "
                    f"{top_level}"
                )
            if (
                source_layer == "builder"
                and ".builder.agents" not in source_module
                and top_level in PROVIDER_MODULES
            ):
                violations.append(
                    f"{source_module}: builder core cannot import provider SDK "
                    f"{top_level}"
                )
            if source_layer == "presentation" and top_level in PROVIDER_MODULES:
                violations.append(
                    f"{source_module}: presentation cannot import provider SDK "
                    f"{top_level}"
                )

    violations.extend(f"import cycle: {' -> '.join(cycle)}" for cycle in _cycles(graph))
    return sorted(set(violations))


def _module_name(path: Path, package_root: Path) -> str:
    relative = path.relative_to(package_root)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join((package_root.name, *parts))


def _imports(
    path: Path,
    source_module: str,
    known_modules: frozenset[str],
) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    source_package = (
        source_module
        if path.name == "__init__.py"
        else source_module.rpartition(".")[0]
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                relative_name = "." * node.level + (node.module or "")
                base = resolve_name(relative_name, source_package)
            else:
                base = node.module or ""
            if base:
                imported.add(base)
            imported.update(
                candidate
                for alias in node.names
                if (candidate := f"{base}.{alias.name}") in known_modules
            )
    return imported


def _layer_of(module: str, package_name: str) -> str | None:
    parts = module.split(".")
    if not parts or parts[0] != package_name or len(parts) < 2:
        return None
    return parts[1]


def _is_stdlib(module: str) -> bool:
    return module == "__future__" or module in sys.stdlib_module_names


def _cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    visited: set[str] = set()
    active: list[str] = []
    active_set: set[str] = set()
    cycles: set[tuple[str, ...]] = set()

    def visit(module: str) -> None:
        if module in active_set:
            start = active.index(module)
            cycle = (*active[start:], module)
            cycles.add(_normalize_cycle(cycle))
            return
        if module in visited:
            return
        active.append(module)
        active_set.add(module)
        for dependency in sorted(graph.get(module, ())):
            visit(dependency)
        active.pop()
        active_set.remove(module)
        visited.add(module)

    for module in sorted(graph):
        visit(module)
    return sorted(cycles)


def _normalize_cycle(cycle: tuple[str, ...]) -> tuple[str, ...]:
    nodes = cycle[:-1]
    rotations = [nodes[index:] + nodes[:index] for index in range(len(nodes))]
    normalized = min(rotations)
    return (*normalized, normalized[0])


def _write_module(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{content}\n", encoding="utf-8")
