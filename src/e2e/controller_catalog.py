"""Credential-free built-in product capabilities published from WindowsAgentArena."""

from __future__ import annotations
import ast
import json
from pathlib import Path
import hashlib
import subprocess
from . import DEFAULT_AGENTCUBE_TEMPLATE
from .common import E2EError

CATALOG = Path(__file__).with_name("builtin_models.json")


def builtin_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def controller_catalog(source: Path):
    source = source.resolve(strict=True)
    tree = source / "src/win-arena-container/wgui"
    astudio = tree / "guest/products/astudio/default_model_config.json"
    workbuddy = tree / "guest/products/workbuddy/model_config.py"
    document = json.loads(astudio.read_text(encoding="utf-8"))
    models = []
    for item in document["models"]:
        if item.get("provider") == "custom" or any(
            item.get(key)
            for key in ["base_url", "api_key", "api_key_env", "url", "model_connection"]
        ):
            continue
        models.append(
            {
                "id": item["id"],
                "display_name": item["label"],
                "reasoning_efforts": [
                    level.casefold() for level in item.get("reasoning_levels", [])
                ],
                "kind": "builtin",
            }
        )
    parsed = ast.parse(workbuddy.read_text(encoding="utf-8"))
    values = None
    for node in parsed.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "BUILTIN_WORKBUDDY_MODELS"
            for target in node.targets
        ):
            if (
                not isinstance(node.value, ast.Call)
                or not isinstance(node.value.func, ast.Name)
                or node.value.func.id != "frozenset"
            ):
                raise E2EError("CONTROLLER_BUILTIN_CATALOG_INVALID")
            values = ast.literal_eval(node.value.args[0])
    if not values or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        raise E2EError("CONTROLLER_BUILTIN_CATALOG_INVALID")
    revision = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return {
        "schema": "wildclawbench.controller-builtin-models/v1",
        "source_revision": revision,
        "source_hashes": {
            path.relative_to(source)
            .as_posix(): hashlib.sha256(path.read_bytes())
            .hexdigest()
            for path in [astudio, workbuddy]
        },
        "products": {
            "astronstudio": {
                "product": "astudio",
                "display_name": "AStudio",
                "models": models,
                "reasoning_efforts": ["none", "high", "max"],
            },
            "workbuddy": {
                "product": "workbuddy",
                "display_name": "WorkBuddy",
                "models": [
                    {"id": value, "display_name": value, "kind": "builtin"}
                    for value in sorted(values, key=str.casefold)
                ],
                "reasoning_efforts": ["none"],
                "max_mode_supported": True,
            },
        },
    }


def profiles_from_catalog(catalog, template=DEFAULT_AGENTCUBE_TEMPLATE):
    return [
        {
            "id": ("astudio" if name == "astronstudio" else name) + "-" + template,
            "harness": name,
            "display_name": product["display_name"],
            "backend": "agentcube",
            "template": template,
            "scenarios": ["general", "web"],
            "enabled": True,
            "models": product["models"],
            "reasoning_efforts": product["reasoning_efforts"],
            "max_mode_supported": product.get("max_mode_supported", False),
            "controller_revision": catalog["source_revision"],
            "model_catalog_source": "windows-agent-arena-builtin",
            "custom_models_supported": False,
            "allow_unlisted_builtin_models": True,
            "default_model": (
                "GLM-5.3"
                if name == "workbuddy"
                else catalog["products"][name]["models"][0]["id"]
            ),
        }
        for name, product in catalog["products"].items()
    ]


def chatgpt_desktop_profile(controller_root: Path, template: str, revision: str) -> dict:
    """Publish the pinned Desktop pilot only for an explicitly supplied template."""
    driver = controller_root / "src/win-arena-container/wgui/guest/products/chatgpt_desktop/ui_driver.py"
    source = driver.read_bytes()
    tree = ast.parse(source)
    required = {"PILOT_MODEL", "PILOT_EFFORT", "PRODUCT_VERSION"}
    wanted = required | {"PILOT_EFFORTS", "PILOT_SCENARIOS", "PILOT_PERMISSION", "MODEL_NAMES"}
    values = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id in wanted):
            values[node.targets[0].id] = ast.literal_eval(node.value)
    if not all(isinstance(values.get(key), str) and values[key] for key in required):
        raise E2EError("CHATGPT_DESKTOP_CONTROLLER_PROFILE_INVALID")
    model, effort = values["PILOT_MODEL"], values["PILOT_EFFORT"]
    efforts = values.get("PILOT_EFFORTS", (effort,))
    scenarios = values.get("PILOT_SCENARIOS", ("general",))
    permission = values.get("PILOT_PERMISSION", "ask for approval")
    if (not isinstance(efforts, (tuple, list)) or effort not in efforts
            or not all(value in ("low", "high") for value in efforts)
            or not isinstance(scenarios, (tuple, list)) or not scenarios
            or not all(value in ("general", "web") for value in scenarios)
            or permission not in ("ask for approval", "full access")):
        raise E2EError("CHATGPT_DESKTOP_CONTROLLER_PROFILE_INVALID")
    models = values.get("MODEL_NAMES", {model: model})
    if (not isinstance(models, dict) or model not in models
            or not all(isinstance(key, str) and key.startswith("gpt-")
                       and isinstance(label, str) and label for key, label in models.items())):
        raise E2EError("CHATGPT_DESKTOP_CONTROLLER_MODEL_CATALOG_INVALID")
    return {
        "id": "chatgpt-desktop-" + template,
        "harness": "chatgpt-desktop",
        "display_name": "ChatGPT 桌面端 · Codex Local",
        "backend": "agentcube",
        "template": template,
        "scenarios": list(scenarios),
        "enabled": True,
        "models": [{"id": key, "display_name": label, "reasoning_efforts": list(efforts), "kind": "builtin"}
                   for key, label in models.items()],
        "reasoning_efforts": list(efforts),
        "default_model": model,
        "default_permission": permission,
        "controller_revision": revision,
        "client_version": values["PRODUCT_VERSION"],
        "model_catalog_source": "windows-agent-arena-chatgpt-desktop-pilot",
        "allow_unlisted_builtin_models": False,
        "custom_models_supported": False,
        "driver_sha256": hashlib.sha256(source).hexdigest(),
    }


def default_profiles(template=DEFAULT_AGENTCUBE_TEMPLATE):
    return profiles_from_catalog(builtin_catalog(), template)
