"""Frozen Windows environment preparation inputs and batch bindings."""
from __future__ import annotations

import json
from pathlib import Path
import re
import stat
import struct
import zipfile

from .artifacts import copy_stream_readonly
from .common import E2EError, digest, file_sha256, identifier, read_json


CAPABILITY = "windows-environment-preprocessing"
PROMPT_CAPABILITY = "execution-prompt-plugin-mentions-v1"
INDEPENDENT_PROMPT_CAPABILITY = "execution-independent-plugin-mentions-v1"
PROMPT_STEP_CAPABILITY = "preprocess-prompt-plugin-step-v1"
PROMPT_STEP = "prompt_plugin"
PLUGIN_VALIDATION = "installed-plugin-v1"
KINDS = {"skill", "plugin", "acode", "powershell", PROMPT_STEP}
PROMPT_DIRECTIVE_KEYS = {"default", "overrides"}
EXE = "acode-windows-x64.exe"
MANIFEST = "acode-runtime-manifest.json"
SHA = re.compile(r"[0-9a-f]{64}\Z")
ARCHIVE_LIMIT = {"skill": (50, 100), "plugin": (50, 100), "acode": (512, 768)}
SCRIPT_LIMIT = 256 * 1024
FILE_LIMIT = 100 * 1024 * 1024
TRANSFER_TIMEOUT = 300


def safe_name(value):
    if (not isinstance(value, str) or not value or len(value) > 120
            or value in {".", ".."} or value.endswith((" ", "."))
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
            or re.fullmatch(r"(?i:con|nul|aux|prn|com[0-9¹²³]|lpt[0-9¹²³])(?:\..*)?", value)):
        raise E2EError("PREPROCESS_INVALID_FILE_NAME")
    return value


def archive_files(archive, expanded_mib):
    members = archive.infolist()
    if len(members) > 2000 or sum(row.file_size for row in members) > expanded_mib * 1024 * 1024:
        raise E2EError("PREPROCESS_ARCHIVE_TOO_LARGE")
    entries, files, spellings = {}, {}, {}
    for row in members:
        parts = row.filename.rstrip("/").split("/")
        for part in parts:
            safe_name(part)
        key = tuple(part.casefold() for part in parts)
        for index in range(1, len(parts)):
            normalized = key[:index]
            if spellings.setdefault(normalized, parts[:index]) != parts[:index]:
                raise E2EError("PREPROCESS_ARCHIVE_DIRECTORY_CASE_COLLISION")
        mode = stat.S_IFMT(row.external_attr >> 16)
        if key in entries or mode not in {0, stat.S_IFDIR if row.is_dir() else stat.S_IFREG} or row.flag_bits & 1:
            raise E2EError("PREPROCESS_ARCHIVE_UNSAFE_MEMBER")
        entries[key] = row.is_dir()
        if not row.is_dir():
            files[row.filename] = row
    for key in entries:
        if any(entries.get(key[:index]) is False for index in range(1, len(key))):
            raise E2EError("PREPROCESS_ARCHIVE_FILE_DIRECTORY_COLLISION")
    return files


def _json_member(archive, member):
    if member.file_size > SCRIPT_LIMIT:
        raise E2EError("PREPROCESS_INVALID_PACKAGE_MANIFEST")
    value = json.loads(archive.read(member).decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise E2EError("PREPROCESS_INVALID_PACKAGE_MANIFEST")
    return value


def _skill_name(payload):
    lines = payload.decode("utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        raise E2EError("PREPROCESS_SKILL_FRONTMATTER_REQUIRED")
    names = []
    for line in lines[1:]:
        if line.strip() == "---":
            if len(names) != 1:
                raise E2EError("PREPROCESS_SKILL_NAME_REQUIRED")
            return identifier(names[0], "skill_name")
        if line.startswith("name:"):
            names.append(line[5:].strip().strip("'\""))
    raise E2EError("PREPROCESS_SKILL_FRONTMATTER_REQUIRED")


def _pe_x64(archive, member):
    with archive.open(member) as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise E2EError("PREPROCESS_ACODE_NOT_WINDOWS_X64")
        offset = struct.unpack_from("<I", header, 60)[0]
        if not 64 <= offset <= 1024 * 1024:
            raise E2EError("PREPROCESS_ACODE_NOT_WINDOWS_X64")
        stream.seek(offset)
        if stream.read(6) != b"PE\x00\x00\x64\x86":
            raise E2EError("PREPROCESS_ACODE_NOT_WINDOWS_X64")


def inspect_asset(path: Path, kind: str, name: str):
    import hashlib

    safe_name(name)
    if not isinstance(kind, str) or kind not in (KINDS - {PROMPT_STEP}) | {"file"} or not path.is_file() or path.is_symlink():
        raise E2EError("PREPROCESS_ASSET_INVALID")
    size = path.stat().st_size
    limit = ARCHIVE_LIMIT[kind][0] * 1024 * 1024 if kind in ARCHIVE_LIMIT else (
        SCRIPT_LIMIT if kind == "powershell" else FILE_LIMIT)
    if size == 0 or size > limit:
        raise E2EError("PREPROCESS_ASSET_SIZE_INVALID")
    result = {"kind": kind, "name": name, "size": size, "sha256": file_sha256(path)}
    if kind == "file":
        return result
    if kind == "powershell":
        if not name.lower().endswith(".ps1") or "\0" in path.read_text(encoding="utf-8-sig"):
            raise E2EError("PREPROCESS_SCRIPT_MUST_BE_UTF8_PS1")
        return result
    if not name.lower().endswith(".zip"):
        raise E2EError("PREPROCESS_ZIP_REQUIRED")
    try:
        with zipfile.ZipFile(path) as archive:
            files = archive_files(archive, ARCHIVE_LIMIT[kind][1])
            if kind == "skill":
                targets = {}
                for name, member in files.items():
                    if name.rsplit("/", 1)[-1] != "SKILL.md":
                        continue
                    if member.file_size > SCRIPT_LIMIT:
                        raise E2EError("PREPROCESS_SKILL_DEFINITION_TOO_LARGE")
                    skill = _skill_name(archive.read(member))
                    if skill.casefold() in {key.casefold() for key in targets}:
                        raise E2EError("PREPROCESS_DUPLICATE_SKILL")
                    targets[skill] = name.removesuffix("SKILL.md").rstrip("/")
                if not targets:
                    raise E2EError("PREPROCESS_SKILL_DEFINITION_REQUIRED")
                result["skills"] = targets
            elif kind == "plugin":
                suffixes = {".acode-plugin", ".codex-plugin", ".claude-plugin"}
                manifests = [name for name in files if name.endswith("/plugin.json")
                             and name.split("/")[-2] in suffixes]
                if len(manifests) != 1:
                    raise E2EError("PREPROCESS_SINGLE_PLUGIN_MANIFEST_REQUIRED")
                manifest = manifests[0]
                value = _json_member(archive, files[manifest])
                result["plugin"] = identifier(value.get("name"), "plugin_name")
                result["version"] = identifier(value.get("version"), "plugin_version")
                result["root"] = manifest.rsplit("/", 2)[0] if manifest.count("/") >= 2 else ""
                markets = set()
                for filename, member in files.items():
                    if not filename.endswith("/marketplace.json"):
                        continue
                    market = _json_member(archive, member)
                    entries = market.get("plugins", [])
                    if isinstance(entries, list) and any(isinstance(entry, dict) and entry.get("name") == result["plugin"]
                                                         for entry in entries):
                        name = market.get("name")
                        if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}", name):
                            markets.add(name)
                if markets:
                    result["marketplaces"] = sorted(markets)
            else:
                if not {EXE, MANIFEST}.issubset(files):
                    raise E2EError("PREPROCESS_ACODE_PACKAGE_INCOMPLETE")
                manifest = _json_member(archive, files[MANIFEST])
                expected = {"schemaVersion": 1, "runtime": "acode", "platform": "win32",
                            "arch": "x64", "file": EXE}
                if any(manifest.get(key) != value for key, value in expected.items()):
                    raise E2EError("PREPROCESS_ACODE_MANIFEST_MISMATCH")
                _pe_x64(archive, files[EXE])
                with archive.open(files[EXE]) as stream:
                    binary_sha = hashlib.file_digest(stream, "sha256").hexdigest()
                if manifest.get("sha256") != binary_sha:
                    raise E2EError("PREPROCESS_ACODE_DIGEST_MISMATCH")
                result.update(version=identifier(manifest.get("version"), "acode_version"), binary_sha256=binary_sha)
    except (OSError, KeyError, UnicodeError, RuntimeError, zipfile.BadZipFile) as exc:
        raise E2EError("PREPROCESS_ARCHIVE_INVALID") from exc
    return result


def asset_ref(raw, kind):
    if (not isinstance(raw, dict) or set(raw) != {"sha256", "name", "size", "kind"}
            or raw["kind"] != kind or not SHA.fullmatch(str(raw["sha256"]))
            or type(raw["size"]) is not int or not 1 <= raw["size"] <= 512 * 1024 * 1024):
        raise E2EError("PREPROCESS_ASSET_REFERENCE_INVALID")
    return {**raw, "name": safe_name(raw["name"])}


def normalize_recipe(raw, harness):
    if not isinstance(raw, dict) or set(raw) != {"version_id", "version", "name", "steps"}:
        raise E2EError("PREPROCESS_RECIPE_INVALID")
    if (type(raw["version_id"]) is not int or type(raw["version"]) is not int
            or min(raw["version_id"], raw["version"]) < 1
            or not isinstance(raw["name"], str) or not 1 <= len(raw["name"]) <= 128
            or not isinstance(raw["steps"], list) or not 1 <= len(raw["steps"]) <= 12):
        raise E2EError("PREPROCESS_RECIPE_INVALID")
    targets, steps = set(), []
    for item in raw["steps"]:
        if not isinstance(item, dict) or not isinstance(item.get("kind"), str) or item["kind"] not in KINDS:
            raise E2EError("PREPROCESS_ACTION_INVALID")
        kind = item["kind"]
        if kind == PROMPT_STEP:
            if harness != "astronstudio":
                raise E2EError("PREPROCESS_ACTION_REQUIRES_ASTUDIO")
            if set(item) != {"kind", "plugin_mentions"} or not item["plugin_mentions"]:
                raise E2EError("PREPROCESS_PROMPT_STEP_INVALID")
            if any(step["kind"] == PROMPT_STEP for step in steps):
                raise E2EError("PREPROCESS_PROMPT_STEP_DUPLICATE")
            steps.append({"kind": kind, "plugin_mentions": _normalize_plugin_mentions(item["plugin_mentions"])})
            continue
        base = {"kind", "asset", "timeout"}
        fields = {"skill": {"target", "source"}, "plugin": {"target", "marketplace"},
                  "acode": set(), "powershell": {"attachments"}}[kind]
        if set(item) != base | fields or type(item["timeout"]) is not int or not 10 <= item["timeout"] <= 600:
            raise E2EError("PREPROCESS_ACTION_FIELDS_INVALID")
        if kind != "powershell" and harness != "astronstudio":
            raise E2EError("PREPROCESS_ACTION_REQUIRES_ASTUDIO")
        step = {**item, "asset": asset_ref(item["asset"], kind)}
        if kind in {"skill", "plugin"}:
            identifier(step["target"], "preprocess_target")
        if kind == "skill" and step["source"] not in ("auto", "user", "astudio", "runtime"):
            raise E2EError("PREPROCESS_SKILL_SOURCE_INVALID")
        if kind == "plugin":
            identifier(step["marketplace"], "marketplace")
        if kind == "powershell":
            if not isinstance(step["attachments"], list) or len(step["attachments"]) > 12:
                raise E2EError("PREPROCESS_ATTACHMENTS_INVALID")
            step["attachments"] = [asset_ref(asset, "file") for asset in step["attachments"]]
            names = {asset["name"].casefold() for asset in step["attachments"]}
            if len(names) != len(step["attachments"]):
                raise E2EError("PREPROCESS_ATTACHMENTS_DUPLICATE_NAME")
        else:
            target = tuple(step[key] for key in sorted(fields))
            if (kind, target) in targets:
                raise E2EError("PREPROCESS_DUPLICATE_TARGET")
            targets.add((kind, target))
        steps.append(step)
    if sum(step["timeout"] + 30 for step in steps if step["kind"] != PROMPT_STEP) > 1200:
        raise E2EError("PREPROCESS_TOTAL_TIMEOUT_TOO_LARGE")
    steps = [step for step in steps if step["kind"] != PROMPT_STEP] + [step for step in steps if step["kind"] == PROMPT_STEP]
    return {**raw, "steps": steps}


def _normalize_plugin_mentions(value):
    if not isinstance(value, list) or len(value) > 12:
        raise E2EError("PREPROCESS_PROMPT_DIRECTIVES_INVALID")
    result = []
    for name in value:
        if not isinstance(name, str) or name.startswith("@"):
            raise E2EError("PREPROCESS_PROMPT_PLUGIN_NAME_INVALID")
        result.append(identifier(name, "prompt_plugin_name"))
    if len({name.casefold() for name in result}) != len(result):
        raise E2EError("PREPROCESS_PROMPT_PLUGIN_DUPLICATE")
    return result


def _normalize_prompt_directives(raw):
    if not isinstance(raw, dict) or set(raw) != PROMPT_DIRECTIVE_KEYS or not isinstance(raw["overrides"], dict):
        raise E2EError("PREPROCESS_PROMPT_DIRECTIVES_INVALID")
    return {"default": _normalize_plugin_mentions(raw["default"]),
            "overrides": {identifier(task, "task_id"): _normalize_plugin_mentions(value)
                           for task, value in raw["overrides"].items()}}


def prompt_directives(unit, task_id):
    binding = unit.get("preprocessing") or {}
    recipe = effective(unit, task_id)
    if has_prompt_step(recipe):
        return {"plugin_mentions": recipe_mentions(recipe)}
    raw = binding.get("prompt_directives")
    if not raw:
        return {"plugin_mentions": []}
    mentions = raw["overrides"].get(task_id, raw["default"])
    return {"plugin_mentions": list(mentions)}


def has_prompt_step(recipe):
    return any(step["kind"] == PROMPT_STEP for step in (recipe or {}).get("steps", []))


def recipe_mentions(recipe):
    return [name for step in (recipe or {}).get("steps", []) if step["kind"] == PROMPT_STEP
            for name in step["plugin_mentions"]]


def augment_prompt(prompt, directives, recipe, *, scene="web"):
    """Create a deterministic per-unit Prompt without mutating the source task."""
    if not isinstance(prompt, str) or not isinstance(directives, dict):
        raise E2EError("PREPROCESS_PROMPT_INVALID")
    if set(directives) != {"plugin_mentions"}:
        raise E2EError("PREPROCESS_PROMPT_DIRECTIVES_INVALID")
    mentions = _normalize_plugin_mentions(directives["plugin_mentions"])
    if not mentions:
        return prompt, {"plugin_mentions": [], "changed": False,
                         "base_prompt_sha256": file_sha256_bytes(prompt.encode("utf-8")),
                         "effective_prompt_sha256": file_sha256_bytes(prompt.encode("utf-8"))}
    # Availability is checked in the actual sandbox after environment preparation.
    # A Prompt may name a preinstalled plugin without replacing any files.
    label = "可用 Web 插件：@" if scene == "web" else "可用插件：@"
    block = "\n\n[评测环境插件]\n" + "\n".join(label + name for name in mentions) + "\n"
    effective = prompt + block
    return effective, {"plugin_mentions": list(mentions), "changed": True,
                       "base_prompt_sha256": file_sha256_bytes(prompt.encode("utf-8")),
                       "effective_prompt_sha256": file_sha256_bytes(effective.encode("utf-8"))}


def file_sha256_bytes(value):
    import hashlib
    return hashlib.sha256(value).hexdigest()


def _validate_prompt_directives(unit, task_ids):
    binding = unit.get("preprocessing") or {}
    raw = binding.get("prompt_directives")
    if not raw:
        return
    if set(raw["overrides"]) - set(task_ids):
        raise E2EError("PREPROCESS_PROMPT_OVERRIDE_OUTSIDE_SELECTION")
    if binding.get("prompt_plugin_validation") == PLUGIN_VALIDATION:
        return
    recipes_by_task = {task_id: effective(unit, task_id) for task_id in task_ids}
    for task_id, directives in ((task_id, prompt_directives(unit, task_id)) for task_id in task_ids):
        targets = {step["target"] for step in (recipes_by_task[task_id] or {}).get("steps", [])
                   if step["kind"] == "plugin"}
        missing = [name for name in directives["plugin_mentions"] if name not in targets]
        if missing:
            raise E2EError("PREPROCESS_PROMPT_PLUGIN_NOT_AVAILABLE: " + ",".join(missing))


def execution_prompt(source, base, metadata=None):
    """Read the exact sent bytes from a staging/sealed execution, validating its lock."""
    prompt_path, lock = source / "metadata/effective-prompt.md", source / "metadata/prompt.json"
    if not lock.exists() and not prompt_path.exists():
        if (metadata or {}).get("changed"):
            raise E2EError("EXECUTION_PROMPT_LOCK_MISSING")
        return base
    if not lock.is_file() or not prompt_path.is_file() or lock.is_symlink() or prompt_path.is_symlink():
        raise E2EError("EXECUTION_PROMPT_LOCK_MISSING")
    saved = read_json(lock)
    payload = prompt_path.read_bytes()
    if (saved.get("base_prompt_sha256") != file_sha256_bytes(base)
            or saved.get("effective_prompt_sha256") != file_sha256_bytes(payload)
            or (metadata is not None and saved != metadata)):
        raise E2EError("EXECUTION_PROMPT_DRIFT")
    return payload


def normalize_binding(raw, harness):
    if not isinstance(raw, dict) or set(raw) - {"default", "overrides", "prompt_directives", "prompt_plugin_validation"} \
            or set(raw) & {"default", "overrides"} != {"default", "overrides"} \
            or not isinstance(raw["overrides"], dict):
        raise E2EError("PREPROCESS_BINDING_INVALID")
    default = None if raw["default"] is None else normalize_recipe(raw["default"], harness)
    overrides = {identifier(task, "task_id"): None if value is None else normalize_recipe(value, harness)
                 for task, value in raw["overrides"].items()}
    result = {"default": default, "overrides": overrides}
    recipe_prompt = any(has_prompt_step(recipe) for recipe in (default, *overrides.values()))
    if raw.get("prompt_plugin_validation") not in {None, PLUGIN_VALIDATION}:
        raise E2EError("PROMPT_PLUGIN_VALIDATION_UNSUPPORTED")
    if "prompt_directives" in raw:
        result["prompt_directives"] = _normalize_prompt_directives(raw["prompt_directives"])
        if recipe_prompt and (result["prompt_directives"]["default"] or result["prompt_directives"]["overrides"]):
            raise E2EError("PREPROCESS_PROMPT_CONFIGURATION_CONFLICT")
        if harness != "astronstudio" and any([result["prompt_directives"]["default"],
                                              *result["prompt_directives"]["overrides"].values()]):
            raise E2EError("PREPROCESS_PROMPT_REQUIRES_ASTUDIO")
        if any([result["prompt_directives"]["default"], *result["prompt_directives"]["overrides"].values()]):
            result["prompt_plugin_validation"] = PLUGIN_VALIDATION
    if recipe_prompt:
        result["prompt_plugin_validation"] = PLUGIN_VALIDATION
    return result


def effective(unit, task_id):
    binding = unit.get("preprocessing")
    return binding["overrides"].get(task_id, binding["default"]) if binding else None


def recipes(unit):
    binding = unit.get("preprocessing")
    return [recipe for recipe in (binding["default"], *binding["overrides"].values()) if recipe] if binding else []


def summary(recipe):
    return {key: recipe[key] for key in ("version_id", "version", "name")} if recipe else None


def public_unit(unit):
    return {key: value for key, value in unit.items() if key != "preprocessing"}


def public_plan(plan):
    return {**plan, "units": [public_unit(unit) for unit in plan["units"]]}


def frozen_recipe(batch, unit_id, task_id):
    expected = read_json(batch / "batch.json").get("preprocessing_bindings_sha256")
    if not expected:
        return None
    bindings = read_json(batch / "preprocessing.json")
    if digest(bindings) != expected:
        raise E2EError("PREPROCESS_BINDINGS_DRIFT")
    binding = bindings.get(unit_id)
    return effective({"preprocessing": binding}, task_id)


def frozen_prompt_directives(batch, unit_id, task_id):
    expected = read_json(batch / "batch.json").get("preprocessing_bindings_sha256")
    if not expected:
        return {"plugin_mentions": []}
    bindings = read_json(batch / "preprocessing.json")
    if digest(bindings) != expected:
        raise E2EError("PREPROCESS_BINDINGS_DRIFT")
    return prompt_directives({"preprocessing": bindings.get(unit_id)}, task_id)


def requires_plugin_witness(batch, unit_id):
    expected = read_json(batch / "batch.json").get("preprocessing_bindings_sha256")
    if not expected:
        return False
    bindings = read_json(batch / "preprocessing.json")
    if digest(bindings) != expected:
        raise E2EError("PREPROCESS_BINDINGS_DRIFT")
    policy = (bindings.get(unit_id) or {}).get("prompt_plugin_validation")
    if policy not in {None, PLUGIN_VALIDATION}:
        raise E2EError("PROMPT_PLUGIN_VALIDATION_UNSUPPORTED")
    return policy == PLUGIN_VALIDATION


def selection(units, tasks):
    rows = []
    ids = [task["task_id"] for task in tasks]
    all_ids = set(ids)
    for index, unit in enumerate(units):
        if "preprocessing" not in unit:
            continue
        if set(unit["preprocessing"]["overrides"]) - all_ids:
            raise E2EError("PREPROCESS_OVERRIDE_OUTSIDE_SELECTION")
        _validate_prompt_directives(unit, ids)
        if unit['preprocessing'].get('prompt_plugin_validation') != PLUGIN_VALIDATION and any(prompt_directives(unit, task["task_id"])["plugin_mentions"] and task.get("scene", "web") != "web"
               for task in tasks):
            raise E2EError("PREPROCESS_PROMPT_WEB_ONLY")
        rows.append({"unit_index": index, "unit_id": unit["unit_id"],
                     "cases": [{"task_id": key, "recipe": summary(effective(unit, key)),
                                **({"prompt_directives": prompt_directives(unit, key)}
                                   if unit["preprocessing"].get("prompt_directives") or has_prompt_step(effective(unit, key)) else {})} for key in ids],
                     "binding": unit["preprocessing"]})
    if not rows:
        return {}
    return {"preprocessing_sha256": digest(rows),
            "preprocessing": [{key: value for key, value in row.items() if key != "binding"} for row in rows]}


def freeze_assets(units, source, destination):
    assets = {asset["sha256"]: asset for unit in units for recipe in recipes(unit)
              for step in recipe["steps"] if step["kind"] != PROMPT_STEP
              for asset in (step["asset"], *step.get("attachments", []))}
    if assets and source is None:
        raise E2EError("PREPROCESS_ASSET_DIRECTORY_REQUIRED")
    for sha, asset in assets.items():
        path = source / sha
        checked_asset(path, asset)
        destination.mkdir(mode=0o700, exist_ok=True)
        with path.open("rb") as stream:
            copy_stream_readonly(stream, destination / sha)
        checked_asset(destination / sha, asset)


def checked_asset(path, ref):
    if (path.is_symlink() or not path.is_file() or path.stat().st_size != ref["size"]
            or file_sha256(path) != ref["sha256"]):
        raise E2EError("PREPROCESS_ASSET_CONTENT_DRIFT")


def budget(unit):
    binding = unit.get("preprocessing") or {}
    witness = (2 * 105 + TRANSFER_TIMEOUT + 40
               if binding.get("prompt_plugin_validation") == PLUGIN_VALIDATION or any(has_prompt_step(recipe) for recipe in recipes(unit)) else 0)
    return witness + max((sum(step["timeout"] + 40 + TRANSFER_TIMEOUT for step in recipe["steps"] if step["kind"] != PROMPT_STEP)
                          for recipe in recipes(unit)), default=0)
