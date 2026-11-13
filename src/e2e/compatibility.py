"""Freeze existing scoring Skills and dataset artifacts for a sandbox batch."""
from __future__ import annotations

from pathlib import Path
import hashlib
import io
import json
import os
import zipfile

from .artifacts import _members, extract_zip
from .common import E2EError, atomic_json, file_sha256, inside, load_script, read_json


def verify_installed(batch: Path, scene: str, assets: dict):
    installed = inside(batch, assets["installed_skills"])
    expected = {}

    def check_skill(row, data):
        if hashlib.sha256(data).hexdigest() != row["zip_sha256"]:
            raise E2EError("FROZEN_SKILL_ARCHIVE_DRIFT")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = _members(archive)
            for name, info in members.items():
                if info.is_dir():
                    continue
                parts = name.split("/", 1)
                if len(parts) != 2 or parts[0] != row["name"]:
                    raise E2EError("FROZEN_SKILL_ARCHIVE_ROOT_INVALID")
                expected[name] = hashlib.sha256(archive.read(info)).hexdigest()

    if scene == "general":
        suite = inside(batch, assets["release_suite"])
        if file_sha256(suite) != assets["release_suite_sha256"]:
            raise E2EError("FROZEN_RELEASE_SUITE_DRIFT")
        with zipfile.ZipFile(suite) as archive:
            catalogs = [name for name in archive.namelist() if name.endswith("/release-catalog.json")]
            if len(catalogs) != 1:
                raise E2EError("FROZEN_RELEASE_CATALOG_INVALID")
            prefix = catalogs[0].rsplit("/", 1)[0] + "/"
            catalog = json.loads(archive.read(catalogs[0]))
            for row in catalog["skills"]:
                check_skill(row, archive.read(prefix + row["archive"]))
    else:
        packages = inside(batch, assets["packages"])
        manifest = packages / "skills-build-manifest.json"
        if file_sha256(manifest) != assets["build_manifest_sha256"]:
            raise E2EError("FROZEN_SKILL_BUILD_MANIFEST_DRIFT")
        for row in read_json(manifest)["skills"]:
            check_skill(row, inside(packages, row["archive"]).read_bytes())
    actual = set()
    for directory, dirs, files in os.walk(installed):
        dirs[:] = [name for name in dirs if name not in {"__pycache__", "node_modules"}]
        for name in files:
            path = Path(directory) / name
            relative = path.relative_to(installed).as_posix()
            actual.add(relative)
            if path.is_symlink() or relative not in expected or file_sha256(path) != expected[relative]:
                raise E2EError("FROZEN_INSTALLED_SKILL_DRIFT: " + relative)
    if actual != set(expected):
        raise E2EError("FROZEN_INSTALLED_SKILL_MEMBER_SET_MISMATCH")


def freeze_assets(repo: Path, staging: Path, tasks: list[dict], general_manifest=None, general_members=None) -> dict:
    result = {}
    compatibility = staging / "inputs/compatibility"
    scenes = {task["scene"] for task in tasks}
    if "general" in scenes:
        from eval_general_e2e.datasets.bundle import write_dataset_bundle
        dataset = compatibility / "general" / "dataset.zip"
        write_dataset_bundle(general_manifest, list(general_members.values()), dataset)
        builder = load_script(repo / "tools/e2e-build/build_general_release.py", "sandbox_general_release_builder")
        release_root = compatibility / "general/release"
        release = builder.build_general_release(repo, release_root, release_id="sandbox-general")
        catalog = read_json(release_root / "release-catalog.json")
        installed = compatibility / "general/installed"
        for row in catalog["skills"]:
            archive = release_root / row["archive"]
            extract_zip(archive, installed / row["name"], strip_root=True)
        result["general"] = {"dataset_bundle": dataset.relative_to(staging).as_posix(),
                             "dataset_bundle_sha256": file_sha256(dataset),
                             "dataset_manifest": general_manifest,
                             "release_root": release_root.relative_to(staging).as_posix(),
                             "release_suite": Path(release["suite_path"]).relative_to(staging).as_posix(),
                             "release_suite_sha256": release["suite_sha256"],
                             "installed_skills": installed.relative_to(staging).as_posix()}
    if "web" in scenes:
        builder = load_script(repo / "tools/e2e-build/build_skill_packages.py", "sandbox_web_skill_builder")
        packages = compatibility / "web/packages"
        names = ["score-web-e2e", "orchestrate-web-e2e", "report-web-e2e", "run-web-e2e", "prepare-web-e2e-workspaces"]
        built = builder.build_skill_packages(repo, packages, skill_names=names)
        installed = compatibility / "web/installed"
        for row in built["skills"]:
            extract_zip(packages / row["archive"], installed / row["name"], strip_root=True)
        result["web"] = {"packages": packages.relative_to(staging).as_posix(),
                         "build_manifest_sha256": file_sha256(packages / "skills-build-manifest.json"),
                         "installed_skills": installed.relative_to(staging).as_posix()}
    atomic_json(compatibility / "assets.json", result)
    return result
