"""Restore a new attempt only from the round's SHA-locked execution ZIP."""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def restore(unit, task_id, target):
    unit, target = Path(unit).resolve(), Path(target).absolute()
    assert not target.exists(), "RESTORE_TARGET_EXISTS"
    marker = json.loads((unit / ".general-e2e/round-unit.json").read_text())
    bundle = unit.parent / marker["execution_package"]
    assert digest(bundle.read_bytes()) == marker["execution_sha256"], "EXECUTION_ZIP_DRIFT"
    manifest = json.loads((unit / "manifest.json").read_text())
    task = next(t for t in manifest["tasks"] if t["task_id"] == task_id)
    prefix = None
    with zipfile.ZipFile(bundle) as archive:
        roots = [n for n in archive.namelist() if n.endswith("/manifest.json") and n.count("/") == 1]
        assert len(roots) == 1, "EXECUTION_ZIP_ROOT_AMBIGUOUS"
        assert archive.read(roots[0]) == (unit / "manifest.json").read_bytes(), "EXECUTION_MANIFEST_DRIFT"
        prefix = roots[0].rsplit("/", 1)[0] + "/" + task["workspace"]["path"].rstrip("/") + "/"
        expected = task["workspace"]["entries"]
        # Validate every byte and path before creating anything.
        files = {}
        for entry in expected:
            rel = PurePosixPath(entry["path"])
            assert not rel.is_absolute() and ".." not in rel.parts, "UNSAFE_WORKSPACE_MEMBER"
            if entry["kind"] == "file":
                info = archive.getinfo(prefix + entry["path"])
                assert (info.external_attr >> 16) & 0o170000 != 0o120000, "SYMLINK_IN_ARCHIVE"
                data = archive.read(info)
                assert len(data) == entry["size"] and digest(data) == entry["sha256"], "INITIAL_BYTES_DRIFT"
                files[entry["path"]] = data
        target.mkdir()
        for entry in expected:
            path = target / entry["path"]
            if entry["kind"] == "directory":
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as handle:
                    handle.write(files[entry["path"]])
            path.chmod(int(entry["mode"], 8))
    return {"status": "RESTORED_FROM_FROZEN_EXECUTION_ZIP", "task_id": task_id,
            "execution_zip_sha256": marker["execution_sha256"], "file_count": len(files),
            "new_workspace": str(target)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-root", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    print(json.dumps(restore(args.unit_root, args.task_id, args.target), ensure_ascii=False))
