"""Immutable batch/subset distribution with optional standalone scoring inputs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid
import zipfile

from .artifacts import _members, _protect, extract_zip, freeze_metadata_files, import_execution, inventory, quarantine_local_metadata, remove_temporary_tree, verify_backup, verify_execution
from .common import E2EError, atomic_json, digest, file_sha256, inside, read_json, utc_now
from .engine import load_batch
from .handoff import export_scoring_context
from .store import BatchStore


PACKAGE_SCHEMA = "wildclawbench.sandbox-result-package/v1"


def export_package(batch: Path, output: Path, *, keys: list[str] | None = None, purpose="results", include_unsealed=False) -> dict:
    manifest = load_batch(batch)
    if purpose not in {"results", "scoring"}:
        raise E2EError("EXPORT_PURPOSE_INVALID")
    store = BatchStore(batch)
    rows = store.rows()
    if keys and set(keys) - {row["key"] for row in rows}:
        raise E2EError("EXPORT_EXECUTION_SELECTION_UNKNOWN")
    selected = [row for row in rows if not keys or row["key"] in keys]
    if output.exists() or output.with_suffix(output.suffix + ".json").exists():
        raise E2EError("EXPORT_DESTINATION_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    directory = tempfile.mkdtemp(prefix=".sandbox-export-", dir=output.parent)
    try:
        stage = Path(directory)
        rows_exported = []
        skill_roots = {}
        for row in selected:
            execution = inside(batch, row["execution_root"])
            if not (execution / "backups/backup-receipt.json").exists():
                if keys and not include_unsealed:
                    raise E2EError("SELECTED_EXECUTION_NOT_SEALED")
                continue
            receipt, _ = verify_backup(execution)
            capsule_id = digest(receipt["identity"])
            capsule = stage / "capsules" / capsule_id
            capsule.mkdir(parents=True)
            shutil.copyfile(inside(execution, receipt["archive"]), capsule / "execution-original.zip")
            exported_receipt = {**receipt, "archive": "execution-original.zip"}
            atomic_json(capsule / "receipt.json", exported_receipt)
            entry = {"execution": row, "capsule": capsule.relative_to(stage).as_posix(), "identity": receipt["identity"]}
            supplements = []
            for relative in row.get("supplemental_executions", []):
                source = inside(batch, relative)
                supplemental, _ = verify_backup(source)
                if any(supplemental["identity"].get(key) != value for key, value in receipt["identity"].items()):
                    raise E2EError("SUPPLEMENTAL_EXECUTION_IDENTITY_MISMATCH")
                target = capsule / "supplements" / digest(supplemental["identity"])
                target.mkdir(parents=True)
                shutil.copyfile(inside(source, supplemental["archive"]), target / "execution-original.zip")
                atomic_json(target / "receipt.json", {**supplemental, "archive": "execution-original.zip"})
                supplements.append({"capsule": target.relative_to(stage).as_posix(), "identity": supplemental["identity"]})
            entry["supplements"] = supplements
            if purpose == "scoring" and (execution / "execution-ready.json").exists():
                context_root = stage / "contexts" / capsule_id
                context = export_scoring_context(batch, row["key"], context_root)
                skill_source = Path(context["installed_skills"])
                scene = context["scene"]
                if scene not in skill_roots:
                    target = stage / "skills" / scene
                    shutil.copytree(skill_source, target)
                    skill_roots[scene] = target.relative_to(stage).as_posix()
                entry["scoring_context"] = {**context, "context_root": context_root.relative_to(stage).as_posix(),
                                             "installed_skills": skill_roots[scene]}
                # Export-derived paths are relative; original execution bytes stay intact.
                local_handoff = {**read_json(context_root / "handoff.json"), "installed_skills": skill_roots[scene]}
                atomic_json(context_root / "handoff.json", local_handoff)
            elif purpose == "scoring":
                entry["scoring_unavailable_reason"] = "EXECUTION_NOT_READY_FOR_SCORING"
            rows_exported.append(entry)
        if not rows_exported and not include_unsealed:
            raise E2EError("NO_SEALED_EXECUTIONS_TO_EXPORT")
        atomic_json(stage / "parent-batch.json", manifest)
        index = {"schema": PACKAGE_SCHEMA, "parent_batch_id": batch.name, "parent_batch_sha256": digest(manifest),
                 "purpose": purpose, "created_at": utc_now(), "parent_scope": [row["key"] for row in rows],
                 "exported": rows_exported,
                 "unavailable_executions": [{"execution": row, "reason": "EXECUTION_NOT_SEALED"} for row in selected
                                            if row["key"] not in {entry["execution"]["key"] for entry in rows_exported}],
                 "not_exported": [row["key"] for row in selected if row["key"] not in {entry["execution"]["key"] for entry in rows_exported}]}
        atomic_json(stage / "package-index.json", index)
        (stage / "LOCAL_START.md").write_text(
            "# 本地评分与报告接续\n\n"
            "本包保留完整父范围、执行原件、原生文本与轨迹、备份和回执。\n\n"
            "在本地 WildClawBench 环境使用 eval/run_e2e.py import --workspace-root <本地工作根> "
            "--archive <本ZIP> 完成成员校验、恢复和路径映射。也可通过 --receipt 提供外部校验回执。\n\n"
            "读取生成的 import-receipt.json 中 scoring_contexts。每项 context_root 是本题标准材料，"
            "installed_skills 是包内冻结 Skill 的本机路径。按相应 orchestrate-general-e2e 或 "
            "orchestrate-web-e2e Skill 建立独立单题评分项目，再由 report-general-e2e 或 report-web-e2e "
            "按 parent-batch.json 和 package-index.json 的完整范围汇总。\n\n"
            "purpose=results 只提供原始执行资料。purpose=scoring 另提供成功题的标准评分输入和冻结 Skill。"
            "失败题的 scoring_unavailable_reason、部分轨迹和原始失败资料随包保留。\n",
            encoding="utf-8")
        descriptor = os.open(stage / "package-integrity.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "w", encoding="utf-8") as integrity:
            freeze_metadata_files(stage)
            _protect(stage)
            files = [row for row in inventory(stage) if row["path"] != "package-integrity.json"]
            json.dump({"schema": PACKAGE_SCHEMA, "entries": files}, integrity, ensure_ascii=False, indent=2)
            integrity.flush()
            os.fsync(integrity.fileno())
        temporary = output.with_name("." + output.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for path in sorted(stage.rglob("*")):
                    archive.write(path, path.relative_to(stage).as_posix())
            _verify_package(temporary)
            temporary.rename(output)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        try:
            remove_temporary_tree(Path(directory))
        except OSError as error:
            atomic_json(output.parent / (Path(directory).name + "-cleanup.json"), {
                "schema": "wildclawbench.temporary-cleanup-deferred/v1", "retained_path": directory,
                "error": str(error), "created_at": utc_now()})
    receipt = {"schema": PACKAGE_SCHEMA, "archive": output.name, "archive_sha256": file_sha256(output),
               "purpose": purpose, "parent_batch_id": batch.name, "execution_count": len(rows_exported)}
    atomic_json(output.with_suffix(output.suffix + ".json"), receipt, create=True)
    return receipt


def _verify_package(path: Path) -> dict:
    import hashlib
    with zipfile.ZipFile(path) as archive:
        members = _members(archive)
        document = json.loads(archive.read("package-integrity.json"))
        if document.get("schema") != PACKAGE_SCHEMA:
            raise E2EError("RESULT_PACKAGE_SCHEMA_UNSUPPORTED")
        entries = document["entries"]
        if len({row["path"] for row in entries}) != len(entries):
            raise E2EError("RESULT_PACKAGE_DUPLICATE_ENTRY")
        if set(members) != {row["path"] for row in entries} | {"package-integrity.json"}:
            raise E2EError("RESULT_PACKAGE_MEMBER_SET_MISMATCH")
        for row in entries:
            info = members[row["path"]]
            if info.is_dir() != (row["kind"] == "directory"):
                raise E2EError("RESULT_PACKAGE_MEMBER_TYPE_MISMATCH")
            if row["kind"] == "file":
                if info.file_size != row["size"]:
                    raise E2EError("RESULT_PACKAGE_MEMBER_SIZE_MISMATCH")
                h = hashlib.sha256()
                with archive.open(info) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(chunk)
                if h.hexdigest() != row["sha256"]:
                    raise E2EError("RESULT_PACKAGE_MEMBER_DRIFT: " + row["path"])
        index = json.loads(archive.read("package-index.json"))
        parent = json.loads(archive.read("parent-batch.json"))
        if index.get("schema") != PACKAGE_SCHEMA or digest(parent) != index.get("parent_batch_sha256"):
            raise E2EError("RESULT_PACKAGE_PARENT_BINDING_INVALID")
        return index


def import_package(archive: Path, receipt_path: Path | None, workspace: Path) -> dict:
    index = _verify_package(archive)
    receipt = read_json(receipt_path) if receipt_path else {
        "schema": PACKAGE_SCHEMA, "archive": archive.name, "archive_sha256": file_sha256(archive),
        "purpose": index["purpose"], "parent_batch_id": index["parent_batch_id"]}
    if receipt.get("schema") != PACKAGE_SCHEMA or file_sha256(archive) != receipt.get("archive_sha256"):
        raise E2EError("RESULT_PACKAGE_ARCHIVE_INVALID")
    imports = workspace / "imports"
    imports.mkdir(parents=True, exist_ok=True)
    destination = imports / receipt["archive_sha256"]
    local_receipt = destination / "import-receipt.json"
    if local_receipt.exists():
        previous = read_json(local_receipt)
        if previous.get("archive_sha256") != receipt["archive_sha256"]:
            raise E2EError("IMPORT_DESTINATION_CONFLICT")
        with zipfile.ZipFile(archive) as source:
            entries = json.loads(source.read("package-integrity.json"))["entries"]
        for entry in entries:
            if entry["kind"] == "file":
                path = inside(destination, entry["path"])
                if not path.is_file() or path.stat().st_size != entry["size"] or file_sha256(path) != entry["sha256"]:
                    raise E2EError("IMPORTED_PACKAGE_INPUT_DRIFT")
        for entry in index["exported"]:
            for capsule_entry in [entry, *entry.get("supplements", [])]:
                execution = inside(destination, capsule_entry["capsule"]) / "execution"
                imported_receipt = verify_execution(execution)
                capsule_receipt = read_json(inside(destination, capsule_entry["capsule"]) / "receipt.json")
                if imported_receipt["identity"] != capsule_entry["identity"] or imported_receipt["archive_sha256"] != capsule_receipt["archive_sha256"]:
                    raise E2EError("IMPORTED_CAPSULE_BINDING_DRIFT")
        return {**previous, "status": "already_imported"}
    temporary = imports / (".import-" + uuid.uuid4().hex)
    try:
        extract_zip(archive, temporary, readonly_data=True)
        for entry in index["exported"]:
            context = entry.get("scoring_context")
            if context:
                context_root = inside(temporary, context["context_root"])
                for path in [context_root / "execution-source", *(context_root / "unit").glob("*/tasks/*/workspace")]:
                    if path.is_dir():
                        _protect(path)
        with zipfile.ZipFile(archive) as source:
            expected = json.loads(source.read("package-integrity.json"))["entries"]
        expected_files = {row["path"] for row in expected if row["kind"] == "file"} | {"package-integrity.json"}
        quarantine_local_metadata(temporary, expected_files, imports / ".local-metadata" / uuid.uuid4().hex)
        for row in expected:
            if row["kind"] == "file" and file_sha256(inside(temporary, row["path"])) != row["sha256"]:
                raise E2EError("EXTRACTED_RESULT_PACKAGE_DRIFT: " + row["path"])
        contexts = []
        for entry in index["exported"]:
            for capsule_entry in [entry, *entry.get("supplements", [])]:
                capsule = inside(temporary, capsule_entry["capsule"])
                capsule_receipt = read_json(capsule / "receipt.json")
                if capsule_receipt["identity"] != capsule_entry["identity"]:
                    raise E2EError("IMPORTED_CAPSULE_IDENTITY_MISMATCH")
                import_execution(capsule / "execution-original.zip", capsule / "receipt.json", capsule / "execution")
            if entry.get("scoring_context"):
                context = entry["scoring_context"]
                contexts.append({**context, "context_root": str(inside(destination, context["context_root"])),
                                 "installed_skills": str(inside(destination, context["installed_skills"]))})
        local = {"schema": PACKAGE_SCHEMA, "status": "imported", "archive_sha256": receipt["archive_sha256"],
                 "parent_batch_id": index["parent_batch_id"], "purpose": index["purpose"],
                 "execution_count": len(index["exported"]), "scoring_contexts": contexts, "imported_at": utc_now()}
        atomic_json(temporary / "import-receipt.json", local)
        temporary.rename(destination)
    finally:
        if temporary.exists():
            remove_temporary_tree(temporary)
    return local
