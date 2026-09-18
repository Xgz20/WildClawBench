"""Versioned shared-source bindings for General E2E repository adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Dict, List, Tuple, Union


SOURCE_CATALOG_SCHEMA = "wildclawbench.e2e-shared-source-catalog/v1"
GENERAL_BINDING_SCHEMA = "wildclawbench.general-e2e-adapter-binding/v1"
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


@dataclass(frozen=True)
class SharedComponentSpec:
    name: str
    version: str
    source_root: str
    vendor_root: str
    entrypoints: Tuple[str, ...]


EXPECTED_COMPONENTS: Tuple[SharedComponentSpec, ...] = (
    SharedComponentSpec(
        name="desktop-runtime",
        version="1.0.0",
        source_root="tools/report/e2e-shared/desktop-runtime",
        vendor_root="vendor/e2e-shared/desktop-runtime",
        entrypoints=("process.mjs",),
    ),
    SharedComponentSpec(
        name="desktop-debug",
        version="1.0.1",
        source_root="tools/report/e2e-shared/desktop-debug",
        vendor_root="vendor/e2e-shared/desktop-debug",
        entrypoints=("restart_macos_desktop_debug.sh",),
    ),
    SharedComponentSpec(
        name="resource-metrics",
        version="1.0.0",
        source_root="tools/report/e2e-shared/resource-metrics",
        vendor_root="vendor/e2e-shared/resource-metrics",
        entrypoints=("native-parsers.mjs", "trace-io.mjs"),
    ),
    SharedComponentSpec(
        name="workspace-integrity",
        version="1.0.0",
        source_root="tools/report/e2e-shared/handoff",
        vendor_root="vendor/e2e-shared/handoff",
        entrypoints=("workspace-integrity.mjs",),
    ),
    SharedComponentSpec(
        name="dataset-bundle-verifier",
        version="1.0.1",
        source_root="eval_general_e2e/shared/dataset_bundle",
        vendor_root="vendor/e2e-shared/dataset-bundle",
        entrypoints=("verify.py",),
    ),
    SharedComponentSpec(
        name="grading-core",
        version="0.1.1",
        source_root="src/wildclawbench_grading_core",
        vendor_root="vendor/e2e-shared/wildclawbench_grading_core",
        entrypoints=("__init__.py",),
    ),
    SharedComponentSpec(
        name="general-contracts",
        version="1.0.0",
        source_root="eval_general_e2e/contracts",
        vendor_root="vendor/e2e-shared/general-contracts",
        entrypoints=("validator.py",),
    ),
)

ASTRONSTUDIO_COMPONENT_NAMES = frozenset(
    {"desktop-runtime", "resource-metrics", "workspace-integrity"}
)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def inspect_shared_component_layout(
    repo_root: Union[str, Path],
) -> Dict[str, object]:
    """Validate canonical sources, fixed versions, and the AstronStudio binding."""

    root = Path(repo_root).expanduser().resolve()
    catalog_file = root / "tools/report/e2e-shared/components.json"
    binding_file = root / "eval_general_e2e/adapters/astronstudio/components.json"
    errors: List[Dict[str, str]] = []
    rows: List[Dict[str, object]] = []

    try:
        catalog = _read_json(catalog_file)
    except (OSError, json.JSONDecodeError) as exc:
        catalog = None
        errors.append({"code": "SHARED_COMPONENT_CATALOG_INVALID", "detail": str(exc)})

    actual_components: Dict[str, object] = {}
    if not isinstance(catalog, dict) or catalog.get("schema_version") != SOURCE_CATALOG_SCHEMA:
        if catalog is not None:
            errors.append({
                "code": "SHARED_COMPONENT_CATALOG_INVALID",
                "detail": "source catalog schema mismatch",
            })
    elif not isinstance(catalog.get("components"), list):
        errors.append({
            "code": "SHARED_COMPONENT_CATALOG_INVALID",
            "detail": "components must be an array",
        })
    else:
        for item in catalog["components"]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                errors.append({
                    "code": "SHARED_COMPONENT_CATALOG_INVALID",
                    "detail": "component entry must have a string name",
                })
                continue
            if item["name"] in actual_components:
                errors.append({
                    "code": "SHARED_COMPONENT_CATALOG_INVALID",
                    "detail": f"duplicate component: {item['name']}",
                })
            actual_components[item["name"]] = item

    for expected in EXPECTED_COMPONENTS:
        item = actual_components.get(expected.name)
        row_errors: List[str] = []
        if not isinstance(item, dict):
            row_errors.append("missing catalog entry")
        else:
            if item.get("version") != expected.version or not SEMVER.fullmatch(str(item.get("version", ""))):
                row_errors.append(f"version must be fixed at {expected.version}")
            if item.get("source_root") != expected.source_root:
                row_errors.append("source_root mismatch")
            if item.get("vendor_root") != expected.vendor_root:
                row_errors.append("vendor_root mismatch")
            if tuple(item.get("entrypoints", ())) != expected.entrypoints:
                row_errors.append("entrypoints mismatch")
        component_root = root / expected.source_root
        if not component_root.is_dir() or component_root.is_symlink():
            row_errors.append("source root missing or symbolic link")
        for entrypoint in expected.entrypoints:
            source = component_root / entrypoint
            if not source.is_file() or source.is_symlink():
                row_errors.append(f"entrypoint missing or symbolic link: {entrypoint}")
        if "skills/web-e2e" in expected.source_root:
            row_errors.append("canonical source cannot live under a Web Skill")
        for detail in row_errors:
            errors.append({
                "code": "SHARED_COMPONENT_INVALID",
                "component": expected.name,
                "detail": detail,
            })
        rows.append({
            "name": expected.name,
            "version": expected.version,
            "source_root": expected.source_root,
            "vendor_root": expected.vendor_root,
            "entrypoints": list(expected.entrypoints),
            "valid": not row_errors,
        })

    extra_names = sorted(set(actual_components) - {item.name for item in EXPECTED_COMPONENTS})
    if extra_names:
        errors.append({
            "code": "SHARED_COMPONENT_CATALOG_INVALID",
            "detail": f"unexpected components: {extra_names}",
        })

    try:
        binding = _read_json(binding_file)
    except (OSError, json.JSONDecodeError) as exc:
        binding = None
        errors.append({"code": "GENERAL_ADAPTER_BINDING_INVALID", "detail": str(exc)})
    expected_versions = {
        item.name: item.version
        for item in EXPECTED_COMPONENTS
        if item.name in ASTRONSTUDIO_COMPONENT_NAMES
    }
    if not isinstance(binding, dict) or binding.get("schema_version") != GENERAL_BINDING_SCHEMA:
        if binding is not None:
            errors.append({
                "code": "GENERAL_ADAPTER_BINDING_INVALID",
                "detail": "binding schema mismatch",
            })
    else:
        if binding.get("adapter") != "astronstudio":
            errors.append({
                "code": "GENERAL_ADAPTER_BINDING_INVALID",
                "detail": "adapter must be astronstudio",
            })
        if binding.get("components") != expected_versions:
            errors.append({
                "code": "GENERAL_ADAPTER_BINDING_INVALID",
                "detail": "component versions do not match the source catalog",
            })
        entrypoint = binding.get("entrypoint")
        if entrypoint != "eval_general_e2e/adapters/astronstudio/components.mjs":
            errors.append({
                "code": "GENERAL_ADAPTER_BINDING_INVALID",
                "detail": "entrypoint mismatch",
            })
        elif not (root / entrypoint).is_file():
            errors.append({
                "code": "GENERAL_ADAPTER_BINDING_INVALID",
                "detail": "entrypoint is missing",
            })

    return {
        "schema_version": "wildclawbench.general-e2e-shared-layout-check/v1",
        "status": "PASS" if not errors else "FAIL",
        "catalog": catalog_file.relative_to(root).as_posix(),
        "binding": binding_file.relative_to(root).as_posix(),
        "components": rows,
        "errors": errors,
    }
