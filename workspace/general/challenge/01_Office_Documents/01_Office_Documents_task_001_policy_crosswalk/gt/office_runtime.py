"""Frozen, offline LibreOffice recalculation of disposable XLSX copies.

This helper is intentionally standalone so an identical, hashed copy can live
in a dataset's private scoring materials. It never writes the source workbook.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


LOCK_SCHEMA = "wildclawbench.office-runtime-lock/v1"
AUDIT_SCHEMA = "wildclawbench.office-recalculation/v1"
PROFILE = "offline-xlsx-remove-formula-caches/v1"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024


class OfficeRuntimeError(RuntimeError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _environment(root):
    env = {"PATH": os.defpath, "HOME": str(root / "home"), "TMPDIR": str(root),
           "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8"}
    (root / "home").mkdir(exist_ok=True)
    if os.name == "nt":
        for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        env.update(TEMP=str(root), TMP=str(root))
    return env


def _temporary():
    return tempfile.TemporaryDirectory(prefix="wcb-office-", dir="/private/tmp" if os.sys.platform == "darwin" else None)


def create_office_lock(executable):
    binary = Path(executable).expanduser().resolve(strict=True)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise OfficeRuntimeError("OFFICE_EXECUTABLE_INVALID", str(binary))
    with _temporary() as temporary:
        root = Path(temporary)
        result = subprocess.run([str(binary), "--headless", "--version"], env=_environment(root),
                                cwd=root, capture_output=True, timeout=30)
    version = result.stdout.decode("utf-8", errors="replace").strip()
    if result.returncode or not version.startswith(("LibreOffice ", "LibreOfficeDev ")):
        raise OfficeRuntimeError("OFFICE_VERSION_PROBE_FAILED", version[:300])
    return {"schema_version": LOCK_SCHEMA, "profile": PROFILE, "executable": str(binary),
            "executable_sha256": sha(binary), "engine_version": version}


def validate_office_lock(lock, *, require_executable=True):
    if (not isinstance(lock, dict) or set(lock) != {"schema_version", "profile", "executable", "executable_sha256", "engine_version"}
            or lock.get("schema_version") != LOCK_SCHEMA or lock.get("profile") != PROFILE
            or not isinstance(lock.get("engine_version"), str) or not lock["engine_version"].startswith(("LibreOffice ", "LibreOfficeDev "))
            or not isinstance(lock.get("executable_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", lock["executable_sha256"])):
        raise OfficeRuntimeError("OFFICE_LOCK_INVALID", "Office runtime lock schema/profile mismatch")
    if not isinstance(lock.get("executable"), str) or not lock["executable"]:
        raise OfficeRuntimeError("OFFICE_LOCK_INVALID", "Office executable path must be an absolute string")
    binary = Path(lock["executable"])
    if not binary.is_absolute():
        raise OfficeRuntimeError("OFFICE_LOCK_INVALID", "Office executable path must be absolute")
    if not require_executable:
        return binary
    if not binary.is_file() or binary.is_symlink() or not os.access(binary, os.X_OK):
        raise OfficeRuntimeError("OFFICE_EXECUTABLE_UNAVAILABLE", str(binary))
    if sha(binary) != lock["executable_sha256"]:
        raise OfficeRuntimeError("OFFICE_EXECUTABLE_DRIFT", str(binary))
    return binary


def _clean_package(data):
    """Clear all formula result caches and demand automatic full calculation."""
    try:
        source = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "not an XLSX ZIP") from exc
    cleared = 0
    with source:
        infos = source.infolist()
        if len(infos) > 5000 or sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_BYTES:
            raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "Office package extraction limit")
        if len({info.filename for info in infos}) != len(infos):
            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "duplicate ZIP members")
        names = {info.filename for info in infos}
        if not {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"} <= names:
            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "missing XLSX package parts")
        result = io.BytesIO()
        with zipfile.ZipFile(result, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for info in infos:
                name = info.filename
                parts = name.rstrip("/").split("/")
                if info.flag_bits & 1 or name.startswith("/") or "\\" in name or any(p in {"", ".", ".."} for p in parts):
                    raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsafe/encrypted package member")
                lowered = name.lower()
                if any(token in lowered for token in ("vbaproject", "xl/activex/", "xl/macrosheets/", "xl/embeddings/")):
                    raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "active/embedded content is outside offline recalculation")
                if any(token in lowered for token in ("xl/externallinks/", "xl/connections.xml", "xl/querytables/")):
                    raise OfficeRuntimeError("OFFICE_EXTERNAL_DATA_UNSUPPORTED", "external data needs separate evaluation; no cached result fallback")
                raw = source.read(info)
                if name.endswith(".xml") or name.endswith(".rels"):
                    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "XML entities are unsupported")
                    try:
                        node = ET.fromstring(raw)
                    except ET.ParseError as exc:
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "malformed XML") from exc
                    if name.endswith(".rels") and any(
                        relation.attrib.get("TargetMode") == "External"
                        and not relation.attrib.get("Type", "").endswith("/hyperlink") for relation in node
                    ):
                        raise OfficeRuntimeError("OFFICE_EXTERNAL_DATA_UNSUPPORTED", "active external relationship needs separate evaluation")
                    if name == "[Content_Types].xml" and b"macroenabled" in raw.lower():
                        raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "macro-enabled content type")
                    if name == "xl/workbook.xml":
                        calc = node.find(S + "calcPr")
                        if calc is None:
                            calc = ET.SubElement(node, S + "calcPr")
                        calc.attrib.update(calcMode="auto", fullCalcOnLoad="1", forceFullCalc="1", calcCompleted="0")
                        raw = ET.tostring(node, encoding="utf-8", xml_declaration=True)
                    elif name.startswith("xl/worksheets/") and name.endswith(".xml"):
                        for cell in node.iter(S + "c"):
                            formula = cell.find(S + "f")
                            if formula is None:
                                continue
                            expression = re.sub(r'"(?:""|[^\"])*"|\'(?:\'\'|[^\'])*\'', "", formula.text or "")
                            if re.search(r"\b(?:WEBSERVICE|IMAGE|DDE|RTD|REGISTER|CALL|EXEC)\s*\(", expression, re.I):
                                raise OfficeRuntimeError("OFFICE_EXTERNAL_DATA_UNSUPPORTED", "active/network formula needs separate evaluation")
                            for cached in list(cell.findall(S + "v")) + list(cell.findall(S + "is")):
                                cell.remove(cached)
                            cell.attrib.pop("t", None)
                            cleared += 1
                        raw = ET.tostring(node, encoding="utf-8", xml_declaration=True)
                target.writestr(info, raw)
    return result.getvalue(), cleared


def recalculate_xlsx(source, lock, output_dir, *, timeout_seconds=60):
    source = Path(source)
    if source.is_symlink():
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "source must not be a symlink")
    source = source.resolve(strict=True)
    if not source.is_file() or source.stat().st_size > MAX_INPUT_BYTES:
        raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "workbook unavailable or too large")
    binary = validate_office_lock(lock)
    data = source.read_bytes()
    original_sha = hashlib.sha256(data).hexdigest()
    normalized, cleared = _clean_package(data)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "recalculated.xlsx"
    receipt = destination / "office-audit.json"
    if target.exists() or receipt.exists():
        raise OfficeRuntimeError("OFFICE_OUTPUT_EXISTS", "derived artifacts are immutable; choose a new directory")
    with _temporary() as temporary:
        root = Path(temporary)
        incoming, outgoing = root / "input", root / "output"
        incoming.mkdir(); outgoing.mkdir()
        profile = root / "profile"
        profile.mkdir()
        (incoming / "workbook.xlsx").write_bytes(normalized)
        command = [str(binary), "-env:UserInstallation=" + profile.as_uri(), "--headless", "--invisible", "--norestore",
                   "--convert-to", "xlsx:Calc MS Excel 2007 XML", "--outdir", str(outgoing), str(incoming / "workbook.xlsx")]
        try:
            result = subprocess.run(command, env=_environment(root), cwd=root, capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise OfficeRuntimeError("OFFICE_RECALCULATION_TIMEOUT", "trusted recalculation did not complete") from exc
        converted = outgoing / "workbook.xlsx"
        if result.returncode or not converted.is_file():
            raise OfficeRuntimeError("OFFICE_RECALCULATION_FAILED", result.stderr.decode("utf-8", errors="replace")[-1500:])
        derived = converted.read_bytes()
        stdout = result.stdout.decode("utf-8", errors="replace")[-4000:]
        stderr = result.stderr.decode("utf-8", errors="replace")[-4000:]
    if sha(source) != original_sha:
        raise OfficeRuntimeError("OFFICE_SOURCE_DRIFT", "source workbook changed during recalculation")
    with target.open("xb") as handle:
        handle.write(derived)
    audit = {"schema_version": AUDIT_SCHEMA, "profile": PROFILE, "engine_version": lock["engine_version"],
             "executable_sha256": lock["executable_sha256"], "source_sha256": original_sha,
             "normalized_input_sha256": hashlib.sha256(normalized).hexdigest(), "derived_sha256": sha(target),
             "formula_caches_cleared": cleared, "source_unchanged": True, "stdout": stdout, "stderr": stderr}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    return {"path": str(target), "audit_path": str(receipt), "audit": audit}
