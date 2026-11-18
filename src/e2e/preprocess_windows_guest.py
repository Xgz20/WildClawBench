"""Windows-only worker copied to one owned evaluation VM by the executor."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shutil
import stat
import subprocess
import sys
from threading import Thread
import time
import zipfile


EXE = "acode-windows-x64.exe"
MANIFEST = "acode-runtime-manifest.json"
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
WAIT_GATE = """import pathlib, subprocess, sys, time
gate = pathlib.Path(sys.argv[1])
for _ in range(200):
    if gate.exists():
        sys.exit(subprocess.call(sys.argv[2:]))
    time.sleep(.05)
sys.exit(124)
"""


class StepError(Exception):
    pass


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("min_work", ctypes.c_size_t),
                ("max_work", ctypes.c_size_t), ("process_limit", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io", ctypes.c_uint64 * 6),
                ("memory", ctypes.c_size_t * 4)]


class JobAccounting(ctypes.Structure):
    _fields_ = [("times", ctypes.c_int64 * 4), ("page_faults", wintypes.DWORD),
                ("total_processes", wintypes.DWORD), ("active_processes", wintypes.DWORD),
                ("terminated_processes", wintypes.DWORD)]


def stop_job(kernel, job):
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.QueryInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p,
    ]
    if not kernel.TerminateJobObject(job, 124):
        return False
    deadline = time.monotonic() + 5
    accounting = JobAccounting()
    while time.monotonic() < deadline:
        if not kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None):
            return False
        if accounting.active_processes == 0:
            return True
        time.sleep(.05)
    return False


@contextmanager
def contained_process(argv, cwd, *, env=None, rpc=False, capture=False):
    import uuid

    # The small wrapper waits for assignment before any uploaded code may start.
    # Job close terminates descendants even if PowerShell exits first.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise StepError("WINDOWS_JOB_CREATION_FAILED")
    gate = cwd / (".start-" + uuid.uuid4().hex)
    process = None
    assigned = False
    try:
        limits = ExtendedLimits()
        limits.basic.flags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                              ctypes.byref(limits), ctypes.sizeof(limits)):
            raise StepError("WINDOWS_JOB_LIMIT_FAILED")
        process = subprocess.Popen([sys.executable, "-I", "-c", WAIT_GATE, str(gate), *map(str, argv)],
                                   cwd=cwd, env=env, stdin=subprocess.PIPE if rpc else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE if rpc or capture else subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        assigned = bool(kernel.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle))))
        if not assigned:
            raise StepError("WINDOWS_JOB_ASSIGN_FAILED")
        gate.touch(exist_ok=False)
        yield process
    finally:
        stopped = not assigned or stop_job(kernel, job)
        kernel.CloseHandle(job)
        if process is not None:
            # Also kill the wrapper when assignment itself failed.
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdin:
                process.stdin.close()
            if process.stdout:
                process.stdout.close()
        gate.unlink(missing_ok=True)
        if not stopped:
            raise StepError("WINDOWS_JOB_TERMINATION_UNCONFIRMED")


def run_command(argv, cwd, timeout, *, env=None, capture=False):
    # User PowerShell output is discarded. It can contain arbitrary material.
    with contained_process(argv, cwd, env=env, capture=capture) as process:
        if capture:
            output, _ = process.communicate(timeout=timeout)
        else:
            process.wait(timeout=timeout)
            output = b""
        return process.returncode, output


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _reparse(path):
    return bool(getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def user_path(path):
    if not path.is_absolute() or path.drive.startswith("\\\\"):
        raise StepError("WINDOWS_PRODUCT_PATH_UNSUPPORTED")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(Path.home().resolve()):
        raise StepError("WINDOWS_PRODUCT_PATH_OUTSIDE_PROFILE")
    return resolved


def astudio_paths():
    import winreg

    home = Path.home()
    programs = Path(os.environ["LOCALAPPDATA"]) / "Programs"
    install = user_path(programs / "AStudio")
    if not (install / "AStudio.exe").is_file():
        raise StepError("ASTUDIO_INSTALLATION_NOT_FOUND")
    # The packaged production installation records its actual data and source home in HKCU.
    try:
        registry = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\AStudioStorage", 0,
                                  winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
    except FileNotFoundError:
        data, source = programs / "AStudio Data", home / ".acode"
    else:
        with registry:
            values = {}
            for key in ("ProductionSchemaVersion", "ProductionDataRoot", "ProductionAcodeHome"):
                try:
                    values[key] = winreg.QueryValueEx(registry, key)[0]
                except FileNotFoundError:
                    continue
        if not values:
            data, source = programs / "AStudio Data", home / ".acode"
        elif values.get("ProductionSchemaVersion") in {1, "1"} and {"ProductionDataRoot", "ProductionAcodeHome"} <= values.keys():
            data, source = Path(values["ProductionDataRoot"]), Path(values["ProductionAcodeHome"])
        else:
            raise StepError("ASTUDIO_STORAGE_REGISTRY_INCOMPLETE")
    if os.environ.get("ASTUDIO_HOME") or os.environ.get("SYNARA_HOME"):
        raise StepError("ASTUDIO_STORAGE_OVERRIDE_UNVERIFIED")
    data = user_path(data)
    return install / "resources" / "bin" / EXE, data, source, user_path(data / "acode-home-overlay")


def _processes(cwd, query, timeout=15):
    command = ("$ErrorActionPreference='Stop';" + query)
    status, output = run_command(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                                 cwd, timeout, capture=True)
    if status != 0:
        raise StepError("WINDOWS_PROCESS_DISCOVERY_FAILED")
    return json.loads(output.decode("utf-8-sig").strip())


def quiescent(cwd):
    active = _processes(cwd, "@(Get-CimInstance Win32_Process -Filter "
                        "\"Name='AStudio.exe' OR Name='acode-windows-x64.exe'\").Count | ConvertTo-Json")
    if active:
        raise StepError("ASTUDIO_REPLACEMENT_REQUIRES_STOPPED_CLIENT")


class Runtime:
    def __init__(self, process, timeout):
        self.process, self.timeout = process, timeout
        self.queue = Queue()
        self.counter = 0
        self.deadline = time.monotonic() + timeout
        Thread(target=self._receive, daemon=True).start()

    def _receive(self):
        try:
            while line := self.process.stdout.readline(2 * 1024 * 1024):
                try:
                    reply = json.loads(line)
                except ValueError:
                    continue
                if isinstance(reply, dict) and reply.get("id") is not None:
                    self.queue.put(reply)
        except (OSError, ValueError):
            pass
        finally:
            self.queue.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False).encode() + b"\n")
        self.process.stdin.flush()

    def call(self, method, params):
        self.counter += 1
        self.send({"id": self.counter, "method": method, "params": params})
        try:
            while True:
                reply = self.queue.get(timeout=max(0, self.deadline - time.monotonic()))
                if reply is None:
                    raise StepError("ACODE_HANDSHAKE_CLOSED")
                if reply.get("id") == self.counter:
                    if "error" in reply or not isinstance(reply.get("result"), dict):
                        raise StepError("ACODE_RPC_REJECTED_" + method.upper().replace("/", "_"))
                    return reply["result"]
        except Empty as exc:
            raise StepError("ACODE_RPC_TIMEOUT") from exc


@contextmanager
def runtime(binary, home, cwd, timeout):
    env = os.environ.copy()
    env.update(ACODE_HOME=str(home), CODEX_HOME=str(home))
    with contained_process([binary, "app-server"], cwd, env=env, rpc=True) as process:
        client = Runtime(process, timeout)
        info = client.call("initialize", {"clientInfo": {"name": "wcb-preprocessing", "version": "1"},
                                          "capabilities": {"experimentalApi": True}})
        runtime_home = info.get("codexHome") or info.get("acodeHome")
        if not runtime_home or Path(runtime_home).resolve() != home.resolve() or info.get("platformOs") != "windows":
            raise StepError("ACODE_RUNTIME_HOME_UNVERIFIED")
        client.send({"method": "initialized"})
        yield client


def replace_directory(source, target, work, verify):
    if not target.is_dir() or _reparse(target):
        raise StepError("PREPROCESS_REPLACEMENT_TARGET_UNSAFE")
    if sum(1 for p in target.rglob("*") if _reparse(p)):
        raise StepError("PREPROCESS_REPLACEMENT_TARGET_HAS_LINKS")
    temporary = target.with_name(target.name + ".wcb-" + work.parent.name + "-" + work.name)
    backup = work / "previous"
    if temporary.exists() or backup.exists() or target.drive.casefold() != backup.drive.casefold():
        raise StepError("PREPROCESS_REPLACEMENT_STAGING_UNSAFE")
    shutil.copytree(source, temporary)
    try:
        target.rename(backup)
        try:
            temporary.rename(target)
            return verify(backup)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            backup.rename(target)
            raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def tree(path):
    return {item.relative_to(path).as_posix(): sha(item) for item in sorted(path.rglob("*")) if item.is_file()}


def tree_digest(path):
    return hashlib.sha256(json.dumps(tree(path), sort_keys=True).encode()).hexdigest()


def skill_name(path):
    if not path.is_file() or _reparse(path) or path.stat().st_size > 256 * 1024:
        return None
    content = path.read_text(encoding="utf-8-sig")
    match = re.match(r"(?s)\A---[^\S\r\n]*\r?\n(.*?)\r?\n---[^\S\r\n]*(?:\r?\n|\Z)", content)
    if match:
        result = re.search(r"(?m)^name:[ \t]*([^\r\n]+)", match.group(1))
        if result:
            return result.group(1).strip().strip("'\"")
    return None


def apply_skill(work, step, binary, data, source, home):
    roots = {"user": source / "skills", "astudio": data / "skills", "runtime": home / "skills"}
    candidates = {}
    for key, root in roots.items():
        if step["source"] not in {"auto", key}:
            continue
        if not root.is_dir():
            continue
        root = user_path(root)
        for index, path in enumerate(root.iterdir()):
            if index >= 2000:
                raise StepError("ASTUDIO_SKILL_DIRECTORY_TOO_LARGE")
            if path.is_dir() and not _reparse(path) and skill_name(path / "SKILL.md") == step["target"]:
                candidates[user_path(path)] = key
    if len(candidates) != 1:
        raise StepError("ASTUDIO_SKILL_TARGET_AMBIGUOUS" if candidates else "ASTUDIO_SKILL_TARGET_NOT_FOUND")
    target, origin = next(iter(candidates.items()))
    expected = tree_digest(work / "payload")

    def verify(backup):
        with runtime(binary, home, work, step["timeout"] - 5) as rpc:
            if origin != "runtime":
                rpc.call("skills/extraRoots/set", {"extraRoots": [str(target.parent)]})
            result = rpc.call("skills/list", {"cwds": [str(work)], "forceReload": True})
        for row in result.get("data", []):
            for skill in row.get("skills", []):
                if (skill.get("name") == step["target"] and skill.get("enabled") is True
                        and Path(skill["path"]).resolve() == (target / "SKILL.md").resolve()
                        and tree_digest(target) == expected):
                    return {"before_sha256": tree_digest(backup), "after_sha256": expected}
        raise StepError("ASTUDIO_SKILL_NOT_ACTIVE")

    return replace_directory(work / "payload", target, work, verify)


def find_local_plugin(rpc, step):
    result = rpc.call("plugin/installed", {"cwds": []})
    identity = step["target"] + "@" + step["marketplace"]
    matches = [(market, plugin) for market in result.get("marketplaces", [])
               if market.get("name") == step["marketplace"]
               for plugin in market.get("plugins", []) if plugin.get("id") == identity]
    if len(matches) != 1:
        raise StepError("ASTUDIO_LOCAL_PLUGIN_NOT_FOUND")
    market, plugin = matches[0]
    if (not market.get("path") or plugin.get("source", {}).get("type") != "local"
            or plugin.get("remotePluginId") or plugin.get("managed")
            or plugin.get("installPolicySource") is not None
            or plugin.get("installPolicy") != "AVAILABLE" or plugin.get("availability") != "AVAILABLE"
            or plugin.get("installed") is not True):
        raise StepError("ASTUDIO_PLUGIN_SOURCE_UNSUPPORTED")
    return user_path(Path(market["path"])), Path(plugin["source"]["path"]), plugin


def apply_plugin(work, step, binary, home):
    expected = tree(work / "payload")
    with runtime(binary, home, work, step["timeout"] - 5) as rpc:
        market, source, before = find_local_plugin(rpc, step)
        if _reparse(source):
            raise StepError("ASTUDIO_PLUGIN_SOURCE_UNSAFE")
        source = user_path(source)
        if source == home or market.is_relative_to(source) or home.is_relative_to(source):
            raise StepError("ASTUDIO_PLUGIN_SOURCE_UNSAFE")
        target_cache = home / "plugins" / "cache" / step["marketplace"] / step["target"]

        def verify(backup):
            result = rpc.call("plugin/install", {"marketplacePath": str(market), "pluginName": step["target"]})
            _, _, installed = find_local_plugin(rpc, step)
            cached = user_path(target_cache / step["version"])
            actual = tree(cached)
            if (result.get("installed") is not True or installed.get("enabled") is not True
                    or installed.get("localVersion") != step["version"]
                    or any(actual.get(key) != value for key, value in expected.items())):
                raise StepError("ASTUDIO_PLUGIN_VERIFICATION_FAILED")
            return {"before_sha256": tree_digest(backup), "after_sha256": tree_digest(cached),
                    "version": step["version"]}

        return replace_directory(work / "payload", source, work, verify)


def apply_acode(work, step, binary, home):
    binary = user_path(binary)
    if not binary.is_file() or _reparse(binary) or not binary.with_name(MANIFEST).is_file():
        raise StepError("ASTUDIO_ACODE_TARGET_UNVERIFIED")
    previous = work / "previous"
    previous.mkdir()
    before = sha(binary)
    moved = []
    try:
        for filename in (EXE, MANIFEST):
            current = binary.with_name(filename)
            if _reparse(current):
                raise StepError("ASTUDIO_ACODE_TARGET_UNSAFE")
            current.rename(previous / filename)
            moved.append(current)
            shutil.copyfile(work / "payload" / filename, current)
            if sha(current) != sha(work / "payload" / filename):
                raise StepError("ASTUDIO_ACODE_INSTALL_DIGEST_MISMATCH")
        status, output = run_command([binary, "--version"], work, min(25, step["timeout"] - 5), capture=True)
        if status != 0 or step["version"] not in re.findall(r"[A-Za-z0-9.-]+", output.decode("utf-8")):
            raise StepError("ASTUDIO_ACODE_VERSION_MISMATCH")
        with runtime(binary, home, work, step["timeout"] - 5):
            pass
        return {"before_sha256": before, "after_sha256": sha(binary), "version": step["version"]}
    except Exception:
        for current in reversed(moved):
            (previous / current.name).replace(current)
        raise


def apply(work, step):
    if step["kind"] == "powershell":
        env = os.environ.copy()
        env["WCB_PREPROCESS_ATTACHMENTS"] = str(work / "payload" / "attachments")
        status, _ = run_command(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                                 work / "payload" / "step.ps1"], work, step["timeout"] - 5, env=env)
        if status != 0:
            return {"status": "failed", "error": "POWERSHELL_NONZERO_EXIT", "exit_code": status}
        return {"exit_code": 0}
    quiescent(work)
    binary, data, source, home = astudio_paths()
    if step["kind"] == "skill":
        return apply_skill(work, step, binary, data, source, home)
    if step["kind"] == "plugin":
        return apply_plugin(work, step, binary, home)
    return apply_acode(work, step, binary, home)


def main():
    work = Path(__file__).resolve().parent
    contract = json.loads((work / "step.json").read_text(encoding="utf-8"))
    claim = work / "started"
    # Exclusive claim protects against accidental duplicate transport submissions.
    with claim.open("x"):
        pass
    started = time.monotonic()
    try:
        expected = contract["files"]
        payload = work / "payload"
        package = work / "payload.zip"
        with package.open("xb") as output:
            for part in sorted(work.glob("parts-*/part-*"), key=lambda path: path.name):
                with part.open("rb") as stream:
                    shutil.copyfileobj(stream, output)
        if sha(package) != contract["package_sha256"]:
            raise StepError("WINDOWS_PREPROCESS_ARCHIVE_DRIFT")
        with zipfile.ZipFile(package) as archive:
            if sorted(archive.namelist()) != sorted(expected):
                raise StepError("WINDOWS_PREPROCESS_ARCHIVE_FILES_INVALID")
            archive.extractall(payload)
        if contract["step"]["kind"] == "powershell":
            (payload / "attachments").mkdir(exist_ok=True)
        if tree(payload) != expected:
            raise StepError("WINDOWS_PREPROCESS_PAYLOAD_DRIFT")
        result = {"status": "passed", **apply(work, contract["step"])}
    except subprocess.TimeoutExpired:
        result = {"status": "failed", "error": "PREPROCESS_STEP_TIMEOUT"}
    except StepError as exc:
        result = {"status": "failed", "error": str(exc)}
    except (OSError, KeyError, UnicodeError, ValueError, zipfile.BadZipFile):
        result = {"status": "failed", "error": "WINDOWS_PREPROCESS_WORKER_FAILED"}
    result.update(invocation=contract["invocation"], duration_seconds=round(time.monotonic() - started, 2))
    temporary = work / ".receipt.tmp"
    temporary.write_text(json.dumps(result), encoding="utf-8")
    temporary.replace(work / "receipt.json")


if __name__ == "__main__":
    main()
