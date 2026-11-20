"""Run one frozen recipe in a dedicated sandbox without dispatching an evaluation."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from threading import Event
import time

from .agentcube import AgentCubeConfig, PlatformError
from .backend import DRIVERS, ObservationPaused, WGUI, powershell
from .common import E2EError, atomic_json, identifier, utc_now
from .preparation import normalize_template_binding
from .preprocessing import budget, normalize_recipe
from .protocol import profiles
from .windows_preprocess import apply_recipe, diagnostic_code


CAPABILITY = "windows-preprocess-validation"
RECEIPT = "validation.json"


class ValidationStore:
    """The driver owns temporary jobs, while the UI reads only the public receipt."""

    def __init__(self, root):
        self.path = root / RECEIPT
        self.row = {"key": root.name, "attempt_id": root.name, "execution_root": "execution",
                    "phase": "PREPARING"}
        self.receipt = {"status": "running", "stage": "checking", "cleanup": "not_created",
                        "events": [], "planned_steps": []}
        atomic_json(self.path, self.receipt, create=True)

    def event(self, stage, status, **fields):
        self.receipt["stage"] = stage
        self.receipt["events"].append({"at": utc_now(), "stage": stage, "status": status, **fields})
        atomic_json(self.path, self.receipt)

    def get(self, key):
        return deepcopy(self.row)

    def update(self, key, phase, **fields):
        self.row.update(phase=phase, **deepcopy(fields))
        if "preprocess_receipt" in fields:
            self.receipt["preprocessing"] = deepcopy(fields["preprocess_receipt"])
            atomic_json(self.path, self.receipt)
        return self.get(key)


def _request(raw):
    legacy_fields = {"profile_id", "model", "recipe"}
    if (not isinstance(raw, dict) or set(raw) not in (legacy_fields, legacy_fields | {"template", "template_binding"})
            or not isinstance(raw["profile_id"], str) or not isinstance(raw["model"], str)):
        raise E2EError("PREPROCESS_VALIDATION_REQUEST_INVALID")
    profile = next((item for item in profiles() if item["id"] == raw["profile_id"] and item["enabled"]), None)
    if not profile or profile.get("backend", "agentcube") != "agentcube":
        raise E2EError("PREPROCESS_VALIDATION_PROFILE_UNAVAILABLE")
    if raw["model"] not in {row["id"] for row in profile["models"]}:
        raise E2EError("PREPROCESS_VALIDATION_MODEL_UNAVAILABLE")
    unit = {"harness": profile["harness"], "template": profile["template"], "model": raw["model"]}
    if "template_binding" in raw:
        binding = normalize_template_binding(raw["template_binding"])
        if binding["profile_id"] != profile["id"]:
            raise E2EError("PREPROCESS_VALIDATION_PROFILE_UNAVAILABLE")
        unit["template"] = identifier(raw["template"], "template")
        unit["template_binding"] = binding
    return unit, normalize_recipe(raw["recipe"], unit["harness"])


def _client_version(driver, sid, harness):
    product = {"astronstudio": "AStudio", "workbuddy": "WorkBuddy"}.get(harness)
    if product is None:
        return None
    # Prefer the executable in use. Fall back to the conventional install
    # location documented by WGUI when the product is not running yet.
    script = (
        f"$paths=@(Get-Process -Name '{product}' -ErrorAction SilentlyContinue | "
        "Where-Object {$_.Path} | Select-Object -ExpandProperty Path -Unique);"
        "if($paths.Count -gt 1){return};"
        f"$path=if($paths.Count -eq 1){{$paths[0]}}else{{Join-Path \"$env:LOCALAPPDATA\" 'Programs\\{product}\\{product}.exe'}};"
        "if(Test-Path -LiteralPath $path -PathType Leaf){"
        "[Console]::Write((Get-Item -LiteralPath $path).VersionInfo.ProductVersion)}"
    )
    try:
        output = driver.client.windows_execute(sid, powershell(script), timeout=15).get("output")
    except PlatformError:
        return None
    if isinstance(output, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}", output.strip()):
        return output.strip()
    return None


def run_validation(root: Path, raw: dict, config_path: Path | None, *, stop=None, driver_factory=None):
    identifier(root.name, "preprocess_validation_id")
    if not root.is_dir() or root.is_symlink():
        raise E2EError("PREPROCESS_VALIDATION_DIRECTORY_INVALID")
    store = ValidationStore(root)
    result = store.receipt
    stop = stop if stop is not None else Event()
    sid = None
    driver = None
    try:
        store.event("checking", "running")
        unit, recipe = _request(raw)
        result["planned_steps"] = [step["kind"] for step in recipe["steps"]]
        result["target"] = unit
        config = AgentCubeConfig.load(config_path)
        bound = {**unit, "preprocessing": {"default": recipe, "overrides": {}}}
        if config.required_expire_ttl(0, budget(bound)) > config.expire_ttl:
            raise E2EError("PLATFORM_TTL_TOO_SHORT_FOR_TIMEOUT")
        store.event("checking", "passed")
        factory = driver_factory or DRIVERS[("agentcube", unit["harness"])]
        driver = factory(batch_root=root, store=store, item=store.get(root.name),
                         task={}, unit=unit, config=config, stop_event=stop)
        driver.checkpoint()
        store.event("creating", "running")
        sid = driver.client.create_session()
        result.update(session_id=sid, cleanup="unconfirmed")
        store.update(root.name, "PREPARING", session_id=sid)
        store.event("creating", "passed")
        store.event("health", "running")
        driver._health(sid)
        store.event("health", "passed")
        store.event("bootstrap", "running")
        driver._prepare_runtime(sid)
        version = _client_version(driver, sid, unit["harness"])
        if version:
            result["target"] = {**unit, "client_version": version}
        store.event("bootstrap", "passed")
        store.event("preprocessing", "running")
        apply_recipe(driver, sid, recipe, WGUI, powershell)
        store.event("preprocessing", "passed")
        result["outcome"] = "passed"
    except (ObservationPaused, KeyboardInterrupt):
        result["outcome"] = "interrupted"
        store.event(result["stage"], "failed", error="PREPROCESS_VALIDATION_INTERRUPTED")
    except (E2EError, OSError, ValueError) as exc:
        result["outcome"] = "failed"
        result["error"] = diagnostic_code(exc, "PREPROCESS_VALIDATION_EXECUTOR_FAILED")
        if isinstance(exc, PlatformError):
            if result["stage"] == "creating" and exc.uncertain:
                result["cleanup"] = "unconfirmed"
            provider = diagnostic_code(exc.platform_code, "")
            if provider:
                result["platform_code"] = provider
        store.event(result["stage"], "failed", error=result["error"])
    finally:
        if driver:
            try:
                if sid:
                    store.event("cleanup", "running")
                    for attempt in range(3):
                        try:
                            if driver.client.delete_session(sid).get("confirmed") is True:
                                result["cleanup"] = "released"
                                break
                        except (PlatformError, OSError, ValueError):
                            pass
                        if attempt < 2:
                            time.sleep(1)
                    if result["cleanup"] == "released":
                        store.event("cleanup", "passed")
                    else:
                        store.event("cleanup", "failed", error="PREPROCESS_VALIDATION_CLEANUP_UNCONFIRMED")
            finally:
                driver.client.close()
        if "outcome" not in result:
            result["outcome"] = "failed"
            result["error"] = "PREPROCESS_VALIDATION_EXECUTOR_FAILED"
        result["status"] = "failed" if result["cleanup"] == "unconfirmed" else result["outcome"]
        store.event("finished", result["status"])
    return result
