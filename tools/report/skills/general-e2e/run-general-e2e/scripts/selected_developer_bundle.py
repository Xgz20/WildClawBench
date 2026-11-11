"""Export only the exact execution and scoring attempts selected by a report."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo
import csv
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile

import run_general_e2e as flow

def sha(path):
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def safe(value):
    path = PurePosixPath(value)
    assert value and not path.is_absolute() and ".." not in path.parts and "\\" not in value
    return path

def build(args, shared):
    assert args.canonical_report_archive and args.task_index, "selected export requires a frozen report and explicit selection"
    index_path = args.task_index.resolve()
    prefix, sealed = shared.canonical_report_files(args.canonical_report_archive.resolve())
    with zipfile.ZipFile(args.canonical_report_archive) as report_zip:
        report_bytes = report_zip.read(prefix + "general_e2e_report_data.json")
        data = json.loads(report_bytes)
        index = read(index_path)
        assert index["schema_version"] == "general-e2e-selected-developer-index/v1"
        assert index["report_data_sha256"] == sha256(report_bytes).hexdigest()
        selected = index["selected_tasks"]
        by_key = {(r["unit_id"], r["task_id"]): r for r in selected}
        report_rows = {(r["unit_id"], r["task_id"]): r for r in data["tasks"]}
        assert len(by_key) == len(selected) == index["selected_runs"] == len(report_rows)
        assert by_key.keys() == report_rows.keys()
        names = {u["unit_id"]: shared_name for u in data["units"] for shared_name in
                 [{"astronstudio": "AStudio", "workbuddy": "WorkBuddy", "doubaowork": "DoubaoWork",
                   "qwenwork": "QwenWork"}.get(u["harness"]["id"], u["unit_id"])]}
        assert len(set(names.values())) == len(names)
        for uid in names:
            assert {tid for unit, tid in by_key if unit == uid} == set(data["scope"]["task_ids"])
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        bundle_name = "general-e2e-selected-" + now.strftime("%Y%m%d_%H%M%S")
        output = args.output_root.resolve()
        output.mkdir(parents=True, exist_ok=True)
        destination = output / bundle_name
        staging = output / ("." + bundle_name + ".pending")
        archive = output / (bundle_name + ".zip")
        assert not any(p.exists() for p in (destination, staging, archive))
        staging.mkdir()
        written = set()
        exclusions = []
        source_files = []

        def copy_file(source, relative):
            safe(relative)
            assert relative not in written, relative
            assert source.is_file() and not source.is_symlink()
            flow.reject_secret(source)
            before = sha(source)
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if sys.platform == "darwin":
                subprocess.run(["/bin/cp", "-c", str(source), str(target)], check=True)
            else:
                shutil.copy2(source, target)
            assert sha(target) == before and sha(source) == before, relative
            written.add(relative)
            source_files.append({"path": relative, "source": str(source), "sha256": before,
                                 "size": source.stat().st_size})

        def copy_tree(source, relative, *, score=False):
            assert source.is_dir() and not source.is_symlink()
            excluded = flow.judge_dependency_exclusions(source, PurePosixPath(relative)) if score else []
            skip = {entry["attempt_relative_path"] for entry in excluded}
            for entry in excluded:
                entry["path"] = relative + "/" + entry["attempt_relative_path"]
            exclusions.extend(excluded)
            if score and (source / "runtime").exists():
                exclusions.append({"path": relative + "/runtime", "reason": "disposable scoring runtime; frozen inputs retained"})
                skip.add("runtime")
            def walk(directory):
                for child in sorted(directory.iterdir(), key=lambda p: p.name):
                    rel = child.relative_to(source).as_posix()
                    dest = relative + "/" + rel
                    if rel in skip:
                        continue
                    frozen = not score or "candidate-original" in Path(rel).parts or "private" in Path(rel).parts
                    if not frozen and (child.name in flow.EXCLUDED_NAMES or child.name.endswith(".pyc")):
                        continue
                    mode = child.lstat().st_mode
                    if stat.S_ISDIR(mode):
                        (staging / dest).mkdir(parents=True, exist_ok=True)
                        walk(child)
                    elif stat.S_ISLNK(mode):
                        link = os.readlink(child)
                        flow.safe_symlink_target(PurePosixPath(dest), link)
                        target = staging / dest
                        target.parent.mkdir(parents=True, exist_ok=True)
                        assert not target.exists() and dest not in written
                        target.symlink_to(link)
                        written.add(dest)
                    elif stat.S_ISREG(mode):
                        copy_file(child, dest)
                    else:
                        raise ValueError("unsupported selected artifact " + str(child))
            (staging / relative).mkdir(parents=True, exist_ok=True)
            walk(source)

        ordinal = {task: i + 1 for i, task in enumerate(data["scope"]["task_ids"])}
        tasks = []
        for item in selected:
            uid, tid = item["unit_id"], item["task_id"]
            r = report_rows[uid, tid]
            ep = Path(item["execution_record"])
            assert sha(ep) == item["execution_record_sha256"] == r["lineage"]["execution_record_sha256"]
            execution = read(ep)
            identity = execution["identity"]
            assert identity == {"batch_id": data["batch_id"], "unit_id": uid, "task_id": tid,
                                "attempt_id": r["execution_attempt_id"]}
            assert item["execution_attempt_id"] == identity["attempt_id"]
            assert item["score_status"] == r["score_status"] and item["total_score"] == r["total_score"]
            assert execution["execution"]["business_status"] == r["execution_status"]
            assert execution["prompt"]["send_status"] == "sent"
            unit = Path(item["unit_root"])
            evidence = Path(item["evidence_root"])
            expected_evidence = unit / "evidence/tasks" / tid / identity["attempt_id"]
            assert evidence == expected_evidence
            assert Path(item["candidate_path"]) == unit / execution["candidate"]["path"]
            assert execution["candidate"]["frozen_sha256"] == item["candidate_sha256"]
            h = names[uid]
            evidence_relative = h + "/unit/" + evidence.relative_to(unit).as_posix()
            copy_tree(evidence, evidence_relative)
            execution_relative = h + "/scoring/execution-records/" + tid + ".json"
            copy_file(ep, execution_relative)
            prompt = Path(item["prompt_file"])
            assert sha(prompt) == execution["prompt"]["sha256"] == item["prompt_sha256"]
            prompt_relative = h + "/Tasks/" + tid + "/PROMPT.md"
            copy_file(prompt, prompt_relative)
            trace_relative = h + "/unit/" + execution["evidence"]["trace_index_path"] if execution["evidence"]["trace_index_path"] else None
            transcript_relative = h + "/unit/" + execution["evidence"]["transcript_path"] if execution["evidence"]["transcript_path"] else None
            raw_dir = str(PurePosixPath(trace_relative).parent / "raw") if trace_relative else None
            candidate = h + "/unit/" + execution["candidate"]["path"]
            score_relative = score_directory = contract = None
            if item.get("score_file"):
                sp = Path(item["score_file"])
                assert sha(sp) == item["score_sha256"] == r["lineage"]["score_sha256"]
                score = read(sp)
                assert score["result"]["valid"] is True and r["score_status"] == "valid"
                assert score["identity"]["attempt_id"] == item["scoring_attempt_id"] == r["scoring_attempt_id"]
                assert score["execution"]["record_sha256"] == sha(ep)
                assert score["execution"]["attempt_id"] == identity["attempt_id"]
                assert score["result"]["total_score"] == r["total_score"]
                score_directory = h + "/scoring/attempts/" + uid + "/" + tid + "/" + item["scoring_attempt_id"]
                copy_tree(sp.parent, score_directory, score=True)
                score_relative = score_directory + "/score.json"
                contract = score_directory + "/private/contract.json"
                if item.get("score_verification_receipt"):
                    proof = Path(item["score_verification_receipt"])
                    verified = read(proof)
                    native = json.loads(verified["stdout"])
                    assert verified["exit_code"] == 0 and native["status"] == "PASS"
                    assert native["score_sha256"] == item["score_sha256"]
                    copy_file(proof, h + "/Verification/" + tid + ".json")
            else:
                assert r["score_status"] == "unscored" and item["scoring_attempt_id"] is None
            if item.get("task_materials_root"):
                material_root = Path(item["task_materials_root"])
                for material in item["task_materials_files"]:
                    path = material_root / safe(material["path"])
                    assert sha(path) == material["sha256"] and path.stat().st_size == material["size"]
                copy_tree(material_root, h + "/Tasks/" + tid)
                contract = h + "/Tasks/" + tid + "/private-scoring/contract.json"
            native_prefix = None
            if item.get("native_prefix"):
                proof = item["native_prefix"]
                native = Path(proof["path"])
                assert sha(native) == proof["sha256"] and native.stat().st_size == proof["size"]
                native_prefix = h + "/SupplementalEvidence/" + tid + "/native-sdk-prefix.jsonl"
                copy_file(native, native_prefix)
            task = {"harness": h, "unit_id": uid, "task_id": tid, "task_name": r["task_name"], "ordinal": ordinal[tid],
                    "execution_attempt_id": identity["attempt_id"], "execution_status": r["execution_status"],
                    "scoring_attempt_id": item["scoring_attempt_id"], "score_status": r["score_status"],
                    "score_0_1": r["total_score"], "score_100": r["total_score"] * 100 if r["total_score"] is not None else None,
                    "score_sha256": item["score_sha256"], "execution_record": execution_relative,
                    "candidate_workspace": candidate, "candidate_artifact": evidence_relative + "/candidate/candidate-artifact.json",
                    "transcript": transcript_relative, "trace_index": trace_relative, "raw_trace_directory": raw_dir,
                    "score_file": score_relative, "scoring_directory": score_directory, "grading_contract": contract,
                    "resource_metrics": h + "/unit/" + execution["resource_metrics_path"] if execution.get("resource_metrics_path") else None,
                    "native_prefix": native_prefix, "rollout": native_prefix,
                    "unscored_reason": item.get("unscored_reason")}
            tasks.append(task)
            if len(tasks) % 10 == 0:
                print(json.dumps({"stage": "selected-attempts-copied", "runs": len(tasks), "scope": len(selected)}), flush=True)

        for diagnostic in index.get("diagnostics", []):
            source = Path(diagnostic["source"])
            assert sha(source) == diagnostic["sha256"]
            copy_file(source, diagnostic["path"])

        copy_file(index_path, "SOURCE_SELECTION.json")
        report_names = ["general_e2e_report_data.json", data["artifact_filenames"]["excel"],
                        data["artifact_filenames"]["leader_markdown"], data["artifact_filenames"]["audit_markdown"],
                        "composite-report-receipt.json", "data/score-verification-index.json"]
        for relative in report_names:
            assert relative in sealed
            raw = report_zip.read(prefix + relative)
            p = staging / "Reports" / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
        write(staging / "TASK_INDEX.json", {"schema_version": 1, "tasks": tasks})
        write(staging / "SELECTION.json", {"schema_version": 1, "selected_runs": len(tasks),
              "unique_tasks": data["scope"]["unique_task_count"], "report_data_sha256": index["report_data_sha256"],
              "selection_rule": "exactly one report-selected execution per unit/task and only its selected valid scoring attempt",
              "source_selection_sha256": sha(index_path), "units": [{"unit_id": uid, "harness": h} for uid, h in names.items()]})
        write(staging / "SOURCE_MAP.json", {"schema_version": 1, "files": source_files})
        write(staging / "PACKAGE_EXCLUSIONS.json", {"schema_version": 1, "entries": exclusions})
        shared.UNITS = names
        summaries = [{"unit_id": uid, "harness": h, "selected_runs": sum(t["unit_id"] == uid for t in tasks),
                      "valid_scores": sum(t["unit_id"] == uid and t["score_status"] == "valid" for t in tasks),
                      "raw_trace_present": sum(t["unit_id"] == uid and bool(t["raw_trace_directory"] or t["native_prefix"]) for t in tasks)}
                     for uid, h in names.items()]
        (staging / "INDEX.html").write_text(shared.build_html(tasks, summaries, "Reports/" + data["artifact_filenames"]["excel"]))
        with (staging / "TASK_INDEX.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            fields = list(tasks[0])
            csv_writer = csv.DictWriter(stream, fieldnames=fields)
            csv_writer.writeheader()
            csv_writer.writerows(tasks)
        (staging / "README.md").write_text(
            "# General E2E 最终选中 attempt 研发包\n\n"
            f"本包共 {len(tasks)} 项选中执行。每题保留终稿选中的执行回合和正式评分回合。\n\n"
            "打开 INDEX.html 或 TASK_INDEX.csv 查找产物、轨迹、原始日志和评分证据。\n\n"
            f"有效评分 {index['scoring_results']} 项，空分 {len(tasks)-index['scoring_results']} 项。已选中的真实报错和中断保留在执行证据中。\n"
            "缺少正式轨迹时，入口列 native_prefix 标明现存原生前缀及 unscored_reason 中的原因。\n\n"
            "离线核验执行 python3 VERIFY.py /absolute/path/to/this.zip，或在解压目录执行 python3 VERIFY.py。\n",
            encoding="utf-8")
        verifier = shared.VERIFY_SCRIPT
        marker = "        assert ex['identity']['task_id']==r['task_id']"
        assert marker in verifier
        verifier = verifier.replace(marker, marker + """
        assert ex['identity']['unit_id']==r['unit_id']
        artifact=json.loads(read(r['candidate_artifact']))
        assert artifact['identity']==ex['identity']
        assert artifact['expected_sha256']==ex['candidate']['frozen_sha256']
        tree=hashlib.sha256()
        for entry in artifact['entries']:
            path=r['candidate_workspace']+'/'+entry['path']
            kind_expected=entry['type']
            assert kind(path)==kind_expected, 'candidate member type'
            if kind_expected=='directory':continue
            assert hash_file(path)==entry['sha256'], 'candidate member SHA'
            tree.update(entry['path'].encode()+b'\\0'+kind_expected.encode()+b'\\0'+entry['sha256'].encode()+b'\\n')
        assert tree.hexdigest()==artifact['expected_sha256'], 'candidate tree digest'
        if r.get('native_prefix'):
            assert read(r['native_prefix']), 'missing archived native prefix'
""", 1)
        (staging / "VERIFY.py").write_text(verifier, encoding="utf-8")
        return finalize(staging, destination, archive, now, len(selected), index["scoring_results"], summaries)


def finalize(staging, destination, archive, now, selected_runs, valid_scores, summaries):
    output = destination.parent
    bundle_name = destination.name
    entries = []
    for directory, dirs, files in os.walk(staging, followlinks=False):
        for name in sorted(dirs + files):
            p = Path(directory) / name
            relative = p.relative_to(staging).as_posix()
            if relative == "INTEGRITY.json" or name == ".DS_Store" or name.startswith("._"):
                continue
            info = p.lstat()
            if p.is_symlink():
                raw = os.readlink(p).encode("utf-8", errors="surrogateescape")
                entries.append({"path": relative, "kind": "symlink", "size": len(raw),
                                "sha256": sha256(raw).hexdigest(), "link_target": os.readlink(p), "mode": f"{stat.S_IMODE(info.st_mode):04o}"})
            elif p.is_dir():
                entries.append({"path": relative, "kind": "directory", "size": 0, "mode": f"{stat.S_IMODE(info.st_mode):04o}"})
            else:
                entries.append({"path": relative, "kind": "file", "size": info.st_size, "sha256": sha(p),
                                "mode": f"{stat.S_IMODE(info.st_mode):04o}"})
        dirs[:] = [n for n in dirs if not (Path(directory) / n).is_symlink()]
    entries.sort(key=lambda x: x["path"])
    write(staging / "INTEGRITY.json", {"schema_version": 1, "entries": entries})
    temporary = output / ("." + bundle_name + ".zip.partial")
    print(json.dumps({"stage": "compressing", "files": sum(e["kind"] == "file" for e in entries),
                      "uncompressed_bytes": sum(e["size"] for e in entries)}), flush=True)
    if temporary.exists():
        preserved = output / ("." + bundle_name + ".failed-" + now.strftime("%Y%m%d_%H%M%S") + ".zip")
        assert not preserved.exists()
        temporary.rename(preserved)
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=4, allowZip64=True) as z:
        for e in [*entries, {"path": "INTEGRITY.json", "kind": "file", "mode": "0644"}]:
            relative = e["path"]
            p = staging / relative
            info = zipfile.ZipInfo(bundle_name + "/" + relative + ("/" if e["kind"] == "directory" else ""), now.timetuple()[:6])
            mode = {"directory": stat.S_IFDIR, "file": stat.S_IFREG, "symlink": stat.S_IFLNK}[e["kind"]]
            info.create_system = 3
            info.external_attr = (mode | int(e["mode"], 8)) << 16
            info.compress_type = zipfile.ZIP_STORED if e["kind"] == "directory" else zipfile.ZIP_DEFLATED
            if e["kind"] == "directory":
                z.writestr(info, b"")
            elif e["kind"] == "symlink":
                z.writestr(info, os.readlink(p).encode())
            else:
                with p.open("rb") as src, z.open(info, "w", force_zip64=True) as dst:
                    shutil.copyfileobj(src, dst, 4 * 1024 * 1024)
    print(json.dumps({"stage": "verifying-zip", "archive_bytes": temporary.stat().st_size}), flush=True)
    verified = subprocess.run([sys.executable, str(staging / "VERIFY.py"), str(temporary)],
                              capture_output=True, text=True)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    result = json.loads(verified.stdout)
    assert result["selected_runs"] == selected_runs and result["valid_scores"] == valid_scores
    staging.rename(destination)
    temporary.rename(archive)
    archive_hash = sha(archive)
    archive.with_suffix(".zip.sha256").write_text(archive_hash + "  " + archive.name + "\n")
    result.update(archive=str(archive), bundle_directory=str(destination), archive_sha256=archive_hash,
                  archive_size_bytes=archive.stat().st_size, summaries=summaries)
    write(archive.with_suffix(".verification.json"), result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result


def resume(args, shared):
    assert args.task_index and args.canonical_report_archive
    staging = args.resume_staging.resolve()
    output = args.output_root.resolve()
    assert staging.parent == output and staging.name.startswith(".general-e2e-selected-") and staging.name.endswith(".pending")
    bundle_name = staging.name[1:-len(".pending")]
    destination = output / bundle_name
    archive = output / (bundle_name + ".zip")
    assert not destination.exists() and not archive.exists()
    selection = read(staging / "SELECTION.json")
    index = read(args.task_index)
    assert sha(args.task_index) == selection["source_selection_sha256"]
    assert sha(staging / "Reports/general_e2e_report_data.json") == index["report_data_sha256"] == selection["report_data_sha256"]
    prefix, sealed = shared.canonical_report_files(args.canonical_report_archive)
    assert sealed["general_e2e_report_data.json"]["sha256"] == index["report_data_sha256"]
    origins = read(staging / "SOURCE_MAP.json")
    for item in origins["files"]:
        path = staging / safe(item["path"])
        assert path.stat().st_size == item["size"] and sha(path) == item["sha256"], item["path"]
    source_selection = staging / "SOURCE_SELECTION.json"
    if not source_selection.exists():
        shutil.copy2(args.task_index, source_selection)
    assert sha(source_selection) == selection["source_selection_sha256"]
    data = read(staging / "Reports/general_e2e_report_data.json")
    with zipfile.ZipFile(args.canonical_report_archive) as report_zip:
        material = data.get("publication_materials", {})
        wanted = [material[k] for k in ("feedback", "feedback_zip") if material.get(k)]
        for relative in list(sealed):
            include = any(relative == value or relative.startswith(str(PurePosixPath(value).parent) + "/")
                          for value in wanted if "/" in value) or relative in wanted
            if include:
                path = staging / "Reports" / safe(relative)
                raw = report_zip.read(prefix + relative)
                assert sha256(raw).hexdigest() == sealed[relative]["sha256"]
                if path.exists():
                    assert sha(path) == sealed[relative]["sha256"]
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
    exclusion_path = staging / "PACKAGE_EXCLUSIONS.json"
    exclusions = read(exclusion_path)
    for entry in exclusions["entries"]:
        if entry["path"].startswith(("scoring/AStudio/", "scoring/WorkBuddy/", "scoring/DoubaoWork/")):
            entry["path"] = entry["path"][len("scoring/"):]
    write(exclusion_path, exclusions)
    tasks = read(staging / "TASK_INDEX.json")["tasks"]
    expected = {(r["unit_id"], r["task_id"]):r for r in index["selected_tasks"]}
    assert len(tasks) == len(expected) == index["selected_runs"]
    for task in tasks:
        row = expected[task["unit_id"], task["task_id"]]
        assert task["execution_attempt_id"] == row["execution_attempt_id"]
        assert task["scoring_attempt_id"] == row["scoring_attempt_id"] and task["score_status"] == row["score_status"]
    summaries = [{"unit_id": uid, "harness": h, "selected_runs": sum(t["unit_id"] == uid for t in tasks),
                  "valid_scores": sum(t["unit_id"] == uid and t["score_status"] == "valid" for t in tasks),
                  "raw_trace_present": sum(t["unit_id"] == uid and bool(t["raw_trace_directory"] or t["native_prefix"]) for t in tasks)}
                 for uid,h in {(t["unit_id"],t["harness"]) for t in tasks}]
    print(json.dumps({"stage":"verified-staging-resume","selected_runs":len(tasks),
                      "source_files_verified":len(origins["files"])}),flush=True)
    return finalize(staging,destination,archive,datetime.now(ZoneInfo("Asia/Shanghai")),
                    index["selected_runs"],index["scoring_results"],summaries)
