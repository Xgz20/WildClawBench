"""Static rule-import discovery and runtime dependency catalog validation."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import sys
from typing import Any, Mapping

from .errors import GradingCoreError


DEPENDENCY_CATALOG_SCHEMA = "wildclawbench.general-e2e-rule-dependencies/v1"
_CATALOG_PATH = Path(__file__).with_name("rule-runtime-dependencies.json")


def load_dependency_catalog() -> dict[str, Any]:
    try:
        payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GradingCoreError(
            "DEPENDENCY_CATALOG_INVALID",
            f"cannot read {_CATALOG_PATH.name}: {exc}",
        ) from exc
    return validate_dependency_catalog(payload)


def validate_dependency_catalog(catalog: Mapping[str, Any]) -> dict[str, Any]:
    if catalog.get("schema_version") != DEPENDENCY_CATALOG_SCHEMA:
        raise GradingCoreError(
            "DEPENDENCY_CATALOG_INVALID", "schema_version mismatch"
        )
    dependencies = catalog.get("dependencies")
    if not isinstance(dependencies, list):
        raise GradingCoreError(
            "DEPENDENCY_CATALOG_INVALID", "dependencies must be an array"
        )
    roots: dict[str, dict[str, Any]] = {}
    normalized: list[dict[str, Any]] = []
    for item in dependencies:
        if not isinstance(item, dict):
            raise GradingCoreError(
                "DEPENDENCY_CATALOG_INVALID", "dependency entry must be an object"
            )
        distribution = item.get("distribution")
        import_roots = item.get("import_roots")
        if not isinstance(distribution, str) or not distribution:
            raise GradingCoreError(
                "DEPENDENCY_CATALOG_INVALID", "distribution must be non-empty"
            )
        if (
            not isinstance(import_roots, list)
            or not import_roots
            or any(not isinstance(root, str) or not root for root in import_roots)
        ):
            raise GradingCoreError(
                "DEPENDENCY_CATALOG_INVALID",
                f"{distribution}.import_roots must be non-empty strings",
            )
        for root in import_roots:
            if root in roots:
                raise GradingCoreError(
                    "DEPENDENCY_CATALOG_INVALID",
                    f"duplicate import root: {root}",
                )
            roots[root] = dict(item)
        normalized.append(dict(item))
    return {
        "schema_version": DEPENDENCY_CATALOG_SCHEMA,
        "dependencies": normalized,
        "_by_import_root": roots,
    }


def imported_roots(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise GradingCoreError(
            "RULE_SOURCE_INVALID",
            f"automated_checks is not valid Python: {exc.msg}",
            details={"line": exc.lineno, "offset": exc.offset},
        ) from exc
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                raise GradingCoreError(
                    "RULE_RELATIVE_IMPORT_UNSUPPORTED",
                    "rule scripts cannot use relative imports",
                )
            if node.module:
                roots.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            dynamic = (
                isinstance(node.func, ast.Name) and node.func.id == "__import__"
            ) or (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "importlib"
                and node.func.attr == "import_module"
            )
            if dynamic:
                raise GradingCoreError(
                    "RULE_DYNAMIC_IMPORT_UNSUPPORTED",
                    "dynamic imports cannot be dependency-audited",
                )
    return sorted(roots)


def inspect_dependencies(
    source: str,
    *,
    catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = validate_dependency_catalog(catalog) if catalog is not None else load_dependency_catalog()
    roots = imported_roots(source)
    stdlib_names = set(getattr(sys, "stdlib_module_names", ())) | {
        "__future__",
    }
    stdlib = sorted(root for root in roots if root in stdlib_names)
    external: list[dict[str, Any]] = []
    unknown: list[str] = []
    by_root = normalized["_by_import_root"]
    for root in roots:
        if root in stdlib_names:
            continue
        dependency = by_root.get(root)
        if dependency is None:
            unknown.append(root)
        else:
            external.append(
                {
                    "import_root": root,
                    "distribution": dependency["distribution"],
                    "runtime_assets": list(dependency.get("runtime_assets", [])),
                }
            )
    if unknown:
        raise GradingCoreError(
            "RULE_DEPENDENCY_UNDECLARED",
            f"undeclared rule imports: {unknown}",
            details={"imports": unknown},
        )
    return {
        "imports": roots,
        "stdlib": stdlib,
        "external": external,
    }
