"""Restore frozen filesystem protections after Windows ZIP transport."""
import re
import stat

from .artifacts import _protect, inventory
from .common import E2EError, digest, inside, read_json


def restore_general_permissions(attempt):
    """Change permissions on the imported copy; leave every frozen byte intact."""
    before = inventory(attempt, allow_symlinks=True)
    manifest = read_json(attempt / "attempt-manifest.json")
    paths = manifest.get("paths", {})
    canonical = attempt / "candidate-original"
    if not canonical.is_dir() or canonical.is_symlink():
        raise E2EError("DESKTOP_SCORING_CANONICAL_COPY_INVALID")
    # ZIP transport creates writable directories and may discard DOS readonly
    # attributes. The archived verifier still requires canonical inputs sealed.
    _protect(canonical, allow_symlinks=True)
    gt = inside(attempt, paths.get("gt"))
    observed = {row["path"]: row for row in inventory(gt)}
    entries = manifest.get("private_scoring", {}).get("workspace_entries")
    if not isinstance(entries, list) or len(entries) != len(observed):
        raise E2EError("DESKTOP_SCORING_GT_INVENTORY_INVALID")
    seen = set()
    modes = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise E2EError("DESKTOP_SCORING_GT_PERMISSIONS_INVALID")
        name, mode = entry.get("path"), entry.get("mode")
        value = observed.get(name)
        if (name in seen or value is None or value["kind"] != entry.get("type")
                or not isinstance(mode, str) or not re.fullmatch(r"0[0-7]{3}", mode)):
            raise E2EError("DESKTOP_SCORING_GT_PERMISSIONS_INVALID")
        seen.add(name)
        modes.append((inside(gt, name), int(mode, 8)))
    # Restore the manifest's exact GT modes, rather than relaxing its verifier.
    for path, mode in sorted(modes, key=lambda item: len(item[0].parts), reverse=True):
        path.chmod(mode)
    after = inventory(attempt, allow_symlinks=True)
    files = lambda rows: {row["path"]: ("symlink:" + row["sha256"] if row["kind"] == "symlink" else row["sha256"])
                          for row in rows if row["kind"] in {"file", "symlink"}}
    if files(before) != files(after):
        raise E2EError("DESKTOP_SCORING_IMPORT_CONTENT_DRIFT")
    previous = {row["path"]: row["mode"] for row in before}
    return {"profile": "windows-general-score-import/v1", "content_unchanged": True,
            "file_inventory_sha256": digest(files(after)),
            "permissions": [{"path": row["path"], "before": f"{previous[row['path']]:04o}",
                             "after": f"{stat.S_IMODE(row['mode']):04o}"}
                            for row in after if previous.get(row["path"]) != row["mode"]]}
