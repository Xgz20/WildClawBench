"""Instrument the supplied BVT without importing it until a POC is requested.

The reference script is an explicit trusted input. Its orchestration is reused
to establish protocol compatibility before a production driver is implemented.
"""
from __future__ import annotations

import ast
import base64
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import time
import uuid
import zipfile


POC_SCHEMA = "wildclawbench.agentcube-poc/v1"
SESSIONS_ROOT = (
    r"C:\Users\Docker\AppData\Local\Programs\AStudio Data"
    r"\acode-home-overlay\sessions"
)
EXPECTED_CWD = r"C:\ProgramData\WGUI\workspace\project"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def reference_config(path: Path) -> dict:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "CONFIG" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError("REFERENCE_CONFIG_MISSING")


def redact(value: object, token: str) -> object:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if re.search(r"token|authorization|api.?key|password", str(key), re.I)
            else redact(item, token)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, token) for item in value]
    if isinstance(value, str):
        result = value.replace(token, "[REDACTED]") if token else value
        return re.sub(r"Bearer\s+\S+", "Bearer [REDACTED]", result, flags=re.I)
    return value


def strict_answer(answer: str) -> bool:
    return answer.strip() == "3"


def reference_protocol(module) -> int:
    request = getattr(module, "RUN_REQUEST", None)
    if request is None:
        return 1
    if not isinstance(request, dict) or request.get("schema_version") != 2:
        raise ValueError("REFERENCE_PROTOCOL_UNSUPPORTED")
    return 2


def reference_client_options(module, configuration: dict) -> dict:
    if reference_protocol(module) == 1:
        return {}
    names = ("workload_manager_url", "router_url", "namespace", "template", "app_id", "user_id",
             "auth_token", "active_ttl", "expire_ttl")
    return {name: configuration[name.upper()] for name in names}


def windows_path(value: str) -> str:
    return value.replace("/", "\\").rstrip("\\").casefold()


def windows_execution_result(payload: dict) -> dict:
    """Accept the observed AgentCube envelope and the reference's raw shape."""
    if "code" in payload:
        if payload["code"] != 0:
            raise ValueError("WINDOWS_EXECUTION_BUSINESS_ERROR")
        payload = payload.get("data")
    if not isinstance(payload, dict) or not isinstance(payload.get("output"), str):
        raise ValueError("WINDOWS_EXECUTION_RESPONSE_INVALID")
    return payload


def bind_rollout(raw: bytes, instruction: str, expected_cwd: str = EXPECTED_CWD) -> dict:
    """Bind the exact POC instruction to a native user message and native cwd."""
    user_lines, cwd_lines, session_ids, terminal_lines = [], [], [], []
    terminal_types = {"task_complete", "task_completed", "turn_complete", "turn_completed"}
    for number, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        item = json.loads(line)
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        if item.get("type") == "session_meta" and payload.get("id"):
            session_ids.append(str(payload["id"]))
        if isinstance(payload.get("cwd"), str) and windows_path(payload["cwd"]) == windows_path(expected_cwd):
            cwd_lines.append(number)
        text = None
        if item.get("type") == "event_msg" and payload.get("type") == "user_message":
            text = payload.get("message")
        elif item.get("type") == "response_item" and payload.get("role") == "user":
            text = "\n".join(
                part.get("text", "") for part in payload.get("content", []) if isinstance(part, dict)
            )
        if isinstance(text, str) and instruction.strip() in text.strip():
            user_lines.append(number)
        if payload.get("type") in terminal_types:
            terminal_lines.append(number)
    return {
        "prompt_lines": user_lines,
        "cwd_lines": cwd_lines,
        "session_ids": sorted(set(session_ids)),
        "terminal_lines": terminal_lines,
        "verified": bool(user_lines and cwd_lines and len(set(session_ids)) == 1),
    }


def validate_members(archive: zipfile.ZipFile) -> None:
    seen = set()
    total_size = 0
    for member in archive.infolist():
        name = member.filename.rstrip("/")
        path = PurePosixPath(name)
        if (not name or member.filename.startswith("/") or "\\" in name
                or any(part in {"", ".", ".."} for part in name.split("/"))
                or path.parts[0].endswith(":") or name in seen
                or (member.external_attr >> 16) & 0o170000 == 0o120000):
            raise ValueError("UNSAFE_ARCHIVE_MEMBER")
        seen.add(name)
        total_size += member.file_size
        if len(seen) > 10_000 or total_size > 128 * 1024 * 1024:
            raise ValueError("POC_ARCHIVE_LIMIT_EXCEEDED")


def seal_result(batch: Path, staging: Path) -> dict:
    """Publish a verified backup after every downloaded file is inventoried."""
    files = []
    for path in sorted(staging.rglob("*")):
        if path.is_symlink():
            raise ValueError("SYMLINK_IN_POC_RESULT")
        if path.is_file():
            data = path.read_bytes()
            files.append({"path": path.relative_to(staging).as_posix(), "size": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()})
    write_json(staging / "inventory.json", {"schema": "wildclawbench.execution-inventory/v1", "files": files})
    original = batch / "original"
    if original.exists():
        raise FileExistsError("ORIGINAL_ALREADY_PUBLISHED")
    staging.rename(original)
    backups = batch / "backups"
    backups.mkdir(exist_ok=True)
    temporary = backups / "execution-original.zip.tmp"
    with zipfile.ZipFile(temporary, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(original.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(original).as_posix())
    with zipfile.ZipFile(temporary) as archive:
        validate_members(archive)
        for row in files:
            if hashlib.sha256(archive.read(row["path"])).hexdigest() != row["sha256"]:
                raise ValueError("BACKUP_MEMBER_MISMATCH")
        if archive.testzip() is not None:
            raise ValueError("BACKUP_CRC_MISMATCH")
    archive_path = backups / "execution-original.zip"
    temporary.rename(archive_path)
    receipt = {"schema": "wildclawbench.execution-backup/v1", "created_at": now(),
               "archive": "backups/execution-original.zip", "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
               "file_count": len(files), "inventory_sha256": hashlib.sha256((original / "inventory.json").read_bytes()).hexdigest()}
    write_json(backups / "backup-receipt.json", receipt)
    return receipt


class PocRecorder:
    def __init__(self, batch: Path, token: str, state: dict):
        self.batch, self.token, self.state = batch, token, state

    def persist(self) -> None:
        write_json(self.batch / "poc-state.json", redact(self.state, self.token))

    def event(self, kind: str, **details) -> None:
        event = redact({"at": now(), "type": kind, **details}, self.token)
        with (self.batch / "events.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        print(json.dumps(event, ensure_ascii=False), flush=True)


def load_reference(path: Path):
    spec = importlib.util.spec_from_file_location("agentcube_bvt_reference", path)
    if spec is None or spec.loader is None:
        raise ValueError("REFERENCE_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_known_creation_state(workspace: Path, configuration: dict) -> None:
    keys = ("WORKLOAD_MANAGER_URL", "APP_ID", "USER_ID", "TEMPLATE", "NAMESPACE")
    for path in (workspace / "batches").glob("*/poc-state.json"):
        previous = json.loads(path.read_text(encoding="utf-8"))
        if previous.get("session_creation") not in {"intent_persisted", "uncertain"}:
            continue
        if all(previous.get("configuration", {}).get(key) == configuration.get(key) for key in keys):
            raise ValueError("UNRESOLVED_SESSION_CREATION: " + str(path.parent))


def run_poc(args) -> int:
    reference = args.reference_script.resolve(strict=True)
    configuration = reference_config(reference)
    if args.agentcube_config:
        overrides = json.loads(args.agentcube_config.read_text(encoding="utf-8"))
        unknown = set(overrides) - set(configuration)
        if unknown:
            raise ValueError("UNKNOWN_AGENTCUBE_CONFIG_KEYS: " + ",".join(sorted(unknown)))
        configuration.update(overrides)
    configuration["AUTH_TOKEN"] = os.environ.get("AGENTCUBE_AUTH_TOKEN", configuration.get("AUTH_TOKEN", ""))
    if not configuration["AUTH_TOKEN"]:
        raise ValueError("AGENTCUBE_AUTH_TOKEN_REQUIRED")
    if args.template:
        configuration["TEMPLATE"] = args.template
    workspace = args.workspace_root.expanduser().resolve()
    require_known_creation_state(workspace, configuration)
    module = load_reference(reference)
    module.CONFIG = configuration
    protocol = reference_protocol(module)
    materials = []
    materials_root = getattr(module, "WORKSPACE_FILES_DIR", None)
    if materials_root is not None:
        for path in sorted(materials_root.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise ValueError("POC_MATERIAL_NOT_REGULAR_FILE")
            data = path.read_bytes()
            materials.append({"name": path.name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    batch_id = args.batch_id or "poc-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", batch_id):
        raise ValueError("INVALID_BATCH_ID")
    batch = workspace / "batches" / batch_id
    batch.mkdir(parents=True, exist_ok=False)
    batch.chmod(0o700)
    staging = batch / "staging"
    staging.mkdir()
    state = {"schema": POC_SCHEMA, "batch_id": batch_id, "created_at": now(), "phase": "PENDING",
             "source": {"reference_path": str(reference), "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
                        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "controller_protocol": protocol, "workspace_materials": materials},
             "configuration": redact(configuration, configuration["AUTH_TOKEN"]), "steps": [],
             "network": {"trust_env": args.trust_env},
             "session_id": None, "session_creation": "not_requested", "cleanup": "not_required", "verdict": None}
    recorder = PocRecorder(batch, configuration["AUTH_TOKEN"], state)
    recorder.persist()
    recorder.event("POC_STARTED", batch_root=str(batch))
    module.log = lambda message: recorder.event("REFERENCE_LOG", message=message)

    class Client(module.AgentCubeClient):
        def create_session(self):
            state["session_creation"] = "intent_persisted"
            recorder.persist()
            try:
                sid = super().create_session()
            except BaseException:
                if state["session_creation"] == "intent_persisted":
                    state["session_creation"] = "uncertain"
                recorder.persist()
                raise
            state.update(session_id=sid, session_creation="confirmed", cleanup="pending")
            recorder.persist()
            return sid

        def delete_session(self, sid):
            response = self.http.delete(self.session_url_tpl.format(sid=sid), timeout=(10, 30))
            if response.status_code not in {200, 202, 204, 404}:
                raise module.BvtError(f"DELETE_SESSION_HTTP_{response.status_code}")
            if response.status_code == 200 and response.content:
                payload = response.json()
                if payload.get("code", 0) != 0:
                    raise module.BvtError("DELETE_SESSION_BUSINESS_ERROR")
            state["cleanup"] = "accepted_unconfirmed" if response.status_code == 202 else "http_confirmed"
            recorder.persist()

        def read_file(self, sid, remote):
            response = self.http.get(f"{self.files_url}/{remote.lstrip('/')}",
                                     headers={"x-agentcube-session-id": sid}, timeout=(10, 60))
            if response.status_code == 404:
                raise FileNotFoundError(remote)
            response.raise_for_status()
            return response.content

        def _read_file_quiet(self, sid, remote):
            try:
                return self.read_file(sid, remote).decode("utf-8", errors="replace")
            except FileNotFoundError:
                return None

        def _unwrap(self, response, action):
            recorder.event("PLATFORM_RESPONSE", action=action, http_status=response.status_code)
            response_directory = staging / "api"
            response_directory.mkdir(exist_ok=True)
            try:
                body = response.json()
            except ValueError:
                body = response.text[:4096]
            write_json(response_directory / f"{len(list(response_directory.iterdir())):05d}-{action}.json", redact({
                "http_status": response.status_code, "body": body,
                "request_id": response.headers.get("X-Request-ID"),
            }, configuration["AUTH_TOKEN"]))
            if action == "create_session" and 400 <= response.status_code < 500:
                state["session_creation"] = "rejected"
                recorder.persist()
            return super()._unwrap(response, action)

        def list_files(self, sid, remote):
            code = "import json,pathlib;print(json.dumps([p.name for p in pathlib.Path(" + repr(remote) + ").iterdir() if p.is_file()]))"
            result = self.execute_oneshot(sid, "python3 -c " + shlex.quote(code))
            if result.get("exit_code") != 0:
                raise module.BvtError("REMOTE_LIST_FILES_FAILED")
            return json.loads(result["stdout"])

    client = Client(**reference_client_options(module, configuration))
    client.http.trust_env = args.trust_env

    class Flow(module.BvtFlow):
        native_before = None
        native_collection = None

        def _win_exec(self, command, timeout=30.0):
            base = (configuration["ROUTER_URL"].rstrip("/") + "/v1/namespaces/"
                    + configuration["NAMESPACE"] + "/code-interpreters/"
                    + configuration["TEMPLATE"] + "/invocations")
            response = client.http.post(base + "/execute", headers={"x-agentcube-session-id": self.sid},
                                        json={"command": command, "shell": True}, timeout=(10, timeout))
            response.raise_for_status()
            return windows_execution_result(response.json())

        def _native_inventory(self):
            script = (
                "$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';$rows=@();"
                "if(Test-Path -LiteralPath '" + SESSIONS_ROOT + "' -PathType Container){"
                "$rows=@(Get-ChildItem -LiteralPath '" + SESSIONS_ROOT
                + "' -Recurse -Filter 'rollout-*.jsonl' -File | "
                "Select-Object FullName,Length,@{Name='Modified';Expression={$_.LastWriteTimeUtc.Ticks}})};"
                "$out=ConvertTo-Json -InputObject $rows -Compress;"
                "[Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($out)))"
            )
            encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            result = self._win_exec("powershell -NoProfile -NonInteractive -EncodedCommand " + encoded, 60)
            if result.get("returncode", 0) != 0:
                raise ValueError("NATIVE_INVENTORY_EXEC_FAILED")
            rows = json.loads(base64.b64decode(result["output"].strip(), validate=True).decode("utf-8-sig"))
            if not isinstance(rows, list) or len(rows) > 10_000:
                raise ValueError("NATIVE_INVENTORY_INVALID")
            return {row["FullName"]: row for row in rows}

        def task_run(self):
            try:
                self.native_before = self._native_inventory()
                write_json(staging / "native-before.json", self.native_before)
            except Exception as error:
                recorder.event("NATIVE_BASELINE_UNAVAILABLE", error=str(error))
            return super().task_run()

        def _pull_native_rollouts(self, directory):
            after = self._native_inventory()
            write_json(staging / "native-after.json", after)
            before = self.native_before or {}
            changed = [path for path, row in after.items() if before.get(path) != row]
            downloaded = []
            base = (configuration["ROUTER_URL"].rstrip("/") + "/v1/namespaces/"
                    + configuration["NAMESPACE"] + "/code-interpreters/"
                    + configuration["TEMPLATE"] + "/invocations")
            for path in sorted(changed):
                if not windows_path(path).startswith(windows_path(SESSIONS_ROOT) + "\\"):
                    raise ValueError("NATIVE_ROLLOUT_PATH_OUTSIDE_SESSIONS")
                name = path.replace("\\", "/").rsplit("/", 1)[-1]
                if not re.fullmatch(r"rollout-[A-Za-z0-9._-]+\.jsonl", name):
                    raise ValueError("NATIVE_ROLLOUT_FILENAME_INVALID")
                if (directory / name).exists():
                    existing = (directory / name).read_bytes()
                else:
                    existing = None
                response = client.http.post(base + "/file", data={"file_path": path},
                                            headers={"x-agentcube-session-id": self.sid}, timeout=(10, 60))
                response.raise_for_status()
                if len(response.content) != after[path]["Length"]:
                    raise ValueError("NATIVE_ROLLOUT_SIZE_CHANGED")
                if existing is not None and existing != response.content:
                    raise ValueError("NATIVE_ROLLOUT_CHANGED_AFTER_COLLECTION")
                (directory / name).write_bytes(response.content)
                downloaded.append(path)
            self.native_collection = {"baseline_available": self.native_before is not None,
                                      "changed": changed, "downloaded": downloaded}
            write_json(staging / "native-collection.json", self.native_collection)
            return len(downloaded)

        def task_collect(self):
            result = super().task_collect()
            remote_root = "/logs/artifacts/collect" if protocol == 2 else "/workspace/output"
            local_root = staging / ("collect" if protocol == 2 else "workspace")
            code = (
                "import pathlib,zipfile; root=pathlib.Path(" + repr(remote_root) + "); "
                "paths=list(root.rglob('*')); assert not any(p.is_symlink() for p in paths), 'WORKSPACE_SYMLINK'; "
                "z=zipfile.ZipFile('/tmp/poc-workspace.zip','w',zipfile.ZIP_DEFLATED); "
                "[z.write(p,p.relative_to(root).as_posix()) for p in paths if p.is_file()]; z.close()"
            )
            self.run_job("python3 -c " + shlex.quote(code), 120, "archive workspace")
            data = client.read_file(self.sid, "/tmp/poc-workspace.zip")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                validate_members(archive)
                archive.extractall(local_root)
            return result

        def verify_answer(self):
            answer_path = ("/logs/artifacts/collect/workspace/answer.md" if protocol == 2
                           else "/workspace/output/answer.md")
            answer = client.read_file(self.sid, answer_path).decode("utf-8")
            (staging / "answer.md").write_text(answer, encoding="utf-8")
            valid = strict_answer(answer)
            write_json(staging / "answer-verification.json", {"expected": "3", "actual": answer, "valid": valid})
            if not valid:
                raise module.BvtError("ANSWER_MISMATCH_EXPECTED_3")
            return "answer.md == 3"

    flow = Flow(client, staging, False)
    failed = False
    try:
        for attribute, title in module.STEPS:
            state.update(phase="RUNNING", current_step=attribute)
            recorder.persist()
            recorder.event("STEP_STARTED", step=attribute, title=title)
            started = time.monotonic()
            try:
                detail = getattr(flow, attribute)()
                row = {"step": attribute, "status": "completed", "seconds": time.monotonic() - started, "detail": detail}
            except Exception as error:
                failed = True
                row = {"step": attribute, "status": "failed", "seconds": time.monotonic() - started,
                       "error": type(error).__name__ + ": " + str(error)}
            state["steps"].append(redact(row, configuration["AUTH_TOKEN"]))
            recorder.persist()
            recorder.event("STEP_FINISHED", **row)
            if failed:
                break
        if not failed:
            bindings = []
            for path in sorted((staging / "trajectory").glob("rollout-*.jsonl")):
                binding = bind_rollout(path.read_bytes(), module.INSTRUCTION,
                                       getattr(module, "GUEST_WORKSPACE", EXPECTED_CWD))
                bindings.append({"path": path.relative_to(staging).as_posix(), **binding})
            collection = flow.native_collection or {}
            state["trajectory_binding_verified"] = sum(row["verified"] for row in bindings) == 1
            covered = (collection.get("baseline_available") is True
                       and len(collection.get("changed", [])) == len(collection.get("downloaded", []))
                       and state["trajectory_binding_verified"])
            state["trajectory_coverage"] = "complete_observed_changed_files" if covered else "partial"
            write_json(staging / "trajectory-binding.json", {
                "bindings": bindings, "selection": "pre_post_native_inventory", "coverage": state["trajectory_coverage"],
            })
            state["capability_gaps"] = [] if covered else ["bound_complete_native_trajectory_export"]
            failed = not covered
            if failed:
                recorder.event("POC_CAPABILITY_GAPS", gaps=state["capability_gaps"])
    except KeyboardInterrupt:
        failed = True
        state["interrupted"] = True
    except Exception as error:
        failed = True
        state["error"] = str(redact(type(error).__name__ + ": " + str(error), configuration["AUTH_TOKEN"]))
        recorder.event("POC_ERROR", error=state["error"])
    finally:
        if flow.sid:
            if failed:
                try:
                    flow.pull_evidence()
                except Exception as error:
                    recorder.event("FAILURE_EVIDENCE_ERROR", error=str(error))
        try:
            write_json(staging / "metadata/poc-observation.json", redact(state, configuration["AUTH_TOKEN"]))
            state["backup"] = seal_result(batch, staging)
        except Exception as error:
            state["backup_error"] = str(redact(str(error), configuration["AUTH_TOKEN"]))
            failed = True
        if flow.sid:
            if args.keep_on_failure and failed:
                state["cleanup"] = "retained_until_ttl"
            elif state.get("backup_error"):
                state["cleanup"] = "retained_backup_failed"
            else:
                try:
                    client.delete_session(flow.sid)
                except Exception as error:
                    state["cleanup"] = "failed"
                    state["cleanup_error"] = str(redact(str(error), configuration["AUTH_TOKEN"]))
                    failed = True
        if state["session_creation"] == "uncertain":
            state["capability_gaps"] = ["reconcile_unknown_session_creation_before_retry"]
            state["cleanup"] = "unknown_session_may_exist"
        if state["cleanup"] == "accepted_unconfirmed":
            failed = True
        state.update(phase="NEEDS_ATTENTION" if failed else "COMPLETED", finished_at=now(),
                     verdict="FAIL" if failed else "PASS")
        recorder.persist()
        recorder.event("POC_FINISHED", verdict=state["verdict"], batch_root=str(batch), cleanup=state["cleanup"])
        client.http.close()
    return 130 if state.get("interrupted") else 3 if failed else 0
