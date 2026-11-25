"""Publish and read only the maintained frozen release of each case library.

Git history may be consulted by the CI publisher for pre-migration sources.
The deployed evaluator reads verified bundles and never reconstructs history.
Existing batches consume their own frozen inputs instead of this catalog.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import zipfile

from eval_general_e2e.datasets.bundle import (
    BundleMember, build_registered_bundle, compile_dataset,
)
from eval_general_e2e.datasets.catalog import load_registered_dataset
from eval_general_e2e.shared.dataset_bundle.verify import (
    archive_member_type, load_verified_dataset_bundle,
)
from src.case_catalog import library, releases
from .common import E2EError, atomic_json, file_sha256, inside, read_json


ASSET_ROOT = ".wildclawbench-assets"
ASSET_SCHEMA = "wildclawbench.e2e-dataset-assets/v1"


def maintained_releases(repo: Path) -> dict[str, dict]:
    result = {}
    for entry in library(repo)["datasets"].values():
        if entry["scene"] == "general" and "e2e" in entry["modes"]:
            for release in releases(repo, entry):
                result[release["id"]] = release["manifest"]
    return result


def frozen_dataset(repo: Path, dataset: str) -> tuple[dict, list[BundleMember]]:
    try:
        registered = load_registered_dataset(repo, dataset)
    except (OSError, ValueError) as exc:
        raise E2EError("GENERAL_DATASET_UNKNOWN") from exc
    if registered.status != "frozen":
        raise E2EError("GENERAL_DATASET_NOT_FROZEN")
    release_id = registered.definition.dataset_id
    supported = maintained_releases(repo)
    if release_id not in supported:
        raise E2EError("GENERAL_DATASET_RETIRED")
    locked = supported[release_id]
    root = repo / ASSET_ROOT
    if (root / "index.json").is_file():
        index = read_json(root / "index.json")
        if index.get("schema") != ASSET_SCHEMA:
            raise E2EError("GENERAL_DATASET_ASSETS_INVALID")
        rows = index.get("datasets")
        if not isinstance(rows, dict):
            raise E2EError("GENERAL_DATASET_ASSETS_INVALID")
        row = rows.get(release_id)
        if not isinstance(row, dict):
            raise E2EError("GENERAL_DATASET_ASSETS_MISSING")
        if (row.get("archive") != f"datasets/{release_id}.zip"
                or row.get("dataset_digest") != locked["dataset_digest"]):
            raise E2EError("GENERAL_DATASET_ASSETS_INVALID")
        path = inside(root, row["archive"])
        if not path.is_file():
            raise E2EError("GENERAL_DATASET_ASSETS_MISSING")
        if file_sha256(path) != row.get("sha256"):
            raise E2EError("GENERAL_DATASET_ASSETS_DRIFT")
        verified = load_verified_dataset_bundle(path)
        if verified.manifest != locked:
            raise E2EError("GENERAL_DATASET_SOURCE_DRIFT")
        prefix = verified.archive_root + "/"
        members = []
        with zipfile.ZipFile(path) as archive:
            for info in archive.infolist():
                relative = info.filename[len(prefix):]
                if relative == "manifest.json":
                    continue
                members.append(BundleMember(relative, archive.read(info),
                                            archive_member_type(info), (info.external_attr >> 16) & 0o777))
        return verified.manifest, members
    # Source checkouts may build the final release for development. A deployed
    # artifact must provide the bundle; missing assets must not trigger Git.
    if not (repo / ".git").exists() or (repo / ".wildclawbench-revision").exists():
        raise E2EError("GENERAL_DATASET_ASSETS_MISSING")
    manifest, members = compile_dataset(repo, definition=registered.definition,
                                        source_revision=locked["source"]["revision"])
    if manifest != locked:
        raise E2EError("GENERAL_DATASET_SOURCE_DRIFT")
    return manifest, members


def publish(repo: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError(f"dataset asset output already exists: {output}")
    output.mkdir(parents=True)
    rows = {}
    for release_id, locked in maintained_releases(repo).items():
        archive = output / "datasets" / f"{release_id}.zip"
        result = build_registered_bundle(repo, release_id, archive)
        if result["dataset_digest"] != locked["dataset_digest"]:
            raise E2EError("GENERAL_DATASET_SOURCE_DRIFT")
        rows[release_id] = {"archive": archive.relative_to(output).as_posix(),
                            "sha256": result["bundle_sha256"],
                            "dataset_digest": result["dataset_digest"]}
    index = {"schema": ASSET_SCHEMA, "datasets": rows}
    atomic_json(output / "index.json", index)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--output", type=Path)
    action.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    if args.verify:
        result = {release_id: frozen_dataset(repo, release_id)[0]["dataset_digest"]
                  for release_id in maintained_releases(repo)}
    else:
        result = publish(repo, args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
