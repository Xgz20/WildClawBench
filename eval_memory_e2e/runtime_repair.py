"""Audited code-only repairs: frozen inputs and accepted sends never change."""
from pathlib import Path

from .io import (append, archive, digest, lock, publish, read_json, require, safe_file,
                 sha, timestamp, verify_artifact)


def effective_sources(root, manifest):
    implementation = dict(manifest["implementation"])
    drivers = {name: dict(profile.get("driver_sources", {})) for name, profile in manifest["profiles"].items()}
    previous = None
    folder = Path(root) / "runtime-repairs"
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    for index, path in enumerate(files, 1):
        require(path.name == f"{index:04d}.json", "REPAIR_SEQUENCE", path.name)
        data = read_json(safe_file(path, root))
        checksum = safe_file(path.with_suffix(".sha256"), root).read_text().strip()
        require(digest(data) == checksum and data["previous"] == previous
                and data["manifest_sha256"] == digest(manifest), "REPAIR_INTEGRITY", path.name)
        for relative, change in data["implementation_changes"].items():
            require(implementation.get(relative) == change["from"], "REPAIR_SOURCE_CHAIN", relative)
            verify_artifact(root, change["before"]); verify_artifact(root, change["after"])
            require(change["before"]["sha256"] == change["from"] and change["after"]["sha256"] == change["to"],
                    "REPAIR_SOURCE_PROOF", relative)
            implementation[relative] = change["to"]
        for harness, replacements in data["driver_changes"].items():
            require(harness in drivers, "REPAIR_PROFILE_SCOPE", harness)
            for source, change in replacements.items():
                require(drivers[harness].get(source) == change["from"], "REPAIR_SOURCE_CHAIN", source)
                verify_artifact(root, change["before"]); verify_artifact(root, change["after"])
                require(change["before"]["sha256"] == change["from"] and change["after"]["sha256"] == change["to"],
                        "REPAIR_SOURCE_PROOF", source)
                drivers[harness][source] = change["to"]
        previous = checksum
    return implementation, drivers, previous, len(files)


def repair_runtime(root, reason):
    root = Path(root).absolute()
    require(isinstance(reason, str) and reason.strip(), "REPAIR_REASON", "Describe the exact infrastructure fix")
    with lock(root):
        manifest = read_json(safe_file(root / "manifest.json", root))
        require(safe_file(root / "manifest.sha256", root).read_text().strip() == digest(manifest), "MANIFEST_DRIFT", str(root))
        for relative, checksum in manifest["inputs"].items():
            require(sha(safe_file(root / relative, root).read_bytes()) == checksum, "INPUT_DRIFT", relative)
        implementation, drivers, previous, count = effective_sources(root, manifest)
        def change(path, before_hash):
            actual = sha(safe_file(path).read_bytes())
            if actual == before_hash:
                return None
            before = next((candidate for candidate in [root / "runtime-source" / before_hash,
                           root / "runtime-source-before-repair" / before_hash,
                           root / "evidence/blobs" / before_hash] if candidate.is_file()), None)
            require(before is not None and sha(before.read_bytes()) == before_hash,
                    "REPAIR_ORIGINAL_SOURCE_MISSING", str(path))
            return {"from": before_hash, "to": actual, "before": archive(root, before), "after": archive(root, path)}
        implementation_changes, driver_changes = {}, {}
        for relative, expected in implementation.items():
            result = change(Path(__file__).parent / relative, expected)
            if result:
                implementation_changes[relative] = result
        for harness, sources in drivers.items():
            replacements = {}
            for source, expected in sources.items():
                result = change(Path(source), expected)
                if result:
                    replacements[source] = result
            if replacements:
                driver_changes[harness] = replacements
        require(implementation_changes or driver_changes, "NO_RUNTIME_CHANGE", "No code drift to repair")
        record = {"schema": "wildclawbench.memory-runtime-repair/v1", "created_at": timestamp(), "reason": reason,
                  "manifest_sha256": digest(manifest), "previous": previous,
                  "implementation_changes": implementation_changes, "driver_changes": driver_changes,
                  "inputs_changed": False, "model_config_changed": False, "prompt_resend_authorized": False}
        path = root / "runtime-repairs" / f"{count + 1:04d}.json"
        publish(path, record); publish(path.with_suffix(".sha256"), (digest(record) + "\n").encode())
        append(root, "RUNTIME_REPAIR", None, {"path": str(path.relative_to(root)), "sha256": digest(record), "reason": reason})
        return {"status": "RUNTIME_REPAIRED", "repair": str(path), "prompt_resend_authorized": False}
