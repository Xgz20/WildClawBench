"""Frozen LibreOffice operations on disposable copies: XLSX math and Office PDF.

This helper is intentionally standalone so an identical, hashed copy can live
in a dataset's private scoring materials. It never writes the source workbook.
"""
from __future__ import annotations

import hashlib
import copy
from decimal import Decimal, InvalidOperation
import io
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from urllib.parse import unquote, urlsplit


LOCK_SCHEMA = "wildclawbench.office-runtime-lock/v1"
AUDIT_SCHEMA = "wildclawbench.office-recalculation/v1"
PROFILE = "offline-xlsx-remove-formula-caches/v1"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
RENDER_LOCK_SCHEMA = "wildclawbench.office-render-runtime-lock/v1"
MULTI_RENDER_LOCK_SCHEMA = "wildclawbench.office-render-runtime-lock/v2"
MULTI_RENDER_PROFILE = "offline-docx-pptx-to-pdf-with-fonts/v1"
RENDER_AUDIT_SCHEMA = "wildclawbench.office-pptx-render/v1"
RENDER_PROFILE = "offline-pptx-to-pdf-with-fonts/v1"
DOCX_RENDER_AUDIT_SCHEMA = "wildclawbench.office-docx-render/v1"
DOCX_RENDER_PROFILE = "offline-docx-to-pdf-with-fonts/v1"
EMBEDDED_AUDIT_SCHEMA = "wildclawbench.office-embedded-xlsx/v1"
COUNTERFACTUAL_AUDIT_SCHEMA = "wildclawbench.office-xlsx-counterfactual/v1"
COUNTERFACTUAL_PROFILE = "offline-xlsx-numeric-input-change/v1"
MARKER_INTERVENTION_AUDIT_SCHEMA = "wildclawbench.office-xlsx-marker-intervention/v1"
MARKER_INTERVENTION_PROFILE = "offline-xlsx-binary-marker-intervention/v1"
NUMERIC_INTERVENTION_AUDIT_SCHEMA = "wildclawbench.office-xlsx-numeric-intervention/v1"
NUMERIC_INTERVENTION_PROFILE = "offline-xlsx-scalar-numeric-intervention/v1"
RENDER_FILTER = {"ExportHiddenSlides": {"type": "boolean", "value": "true"},
                 "ExportNotesPages": {"type": "boolean", "value": "false"},
                 "ExportOnlyNotesPages": {"type": "boolean", "value": "false"}}
DOCX_RENDER_FILTER = {"ExportNotes": {"type": "boolean", "value": "false"},
                      "ExportNotesInMargin": {"type": "boolean", "value": "false"},
                      "ExportFormFields": {"type": "boolean", "value": "false"},
                      "IsSkipEmptyPages": {"type": "boolean", "value": "false"}}


class OfficeRuntimeError(RuntimeError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validate_content_types(raw):
    # OPC content-type manifests require the default namespace. A prefixed
    # rewrite can be XML-readable while LibreOffice cannot load the package.
    checked=raw.replace(b'\x00',b'').upper()
    if b'<!DOCTYPE' in checked or b'<!ENTITY' in checked:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "content-type XML entities are unsupported")
    namespaces={};root=None
    try:
        for event,value in ET.iterparse(io.BytesIO(raw),events=('start-ns','start')):
            if event=='start-ns':namespaces[value[0]]=value[1]
            else:root=value;break
    except ET.ParseError as exc:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "malformed content-type XML") from exc
    namespace='http://schemas.openxmlformats.org/package/2006/content-types'
    if root is None or root.tag!='{'+namespace+'}Types' or namespaces.get('')!=namespace:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "content-type manifest lacks its default namespace")


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
                if name == "[Content_Types].xml":_validate_content_types(raw)
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


def _numeric_literal(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_CHANGE_INVALID", "numeric literals only")
    text = str(value)
    if len(text) > 64 or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?", text):
        raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_CHANGE_INVALID", "invalid numeric literal")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_CHANGE_INVALID", "invalid numeric literal") from exc
    if not number.is_finite() or abs(number) > Decimal("1e15") or (number and number.adjusted() < -15):
        raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_CHANGE_INVALID", "numeric literal outside supported range")
    if not number:
        return "0"
    literal = format(number, "f")
    return literal.rstrip("0").rstrip(".") if "." in literal else literal


def _counterfactual_parts(data, changes):
    """Replay declared numeric input edits without changing formulas or other parts."""
    _clean_package(data)  # bounded, offline package validation; do not use its cache-cleared bytes
    if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
        raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_CHANGE_INVALID", "need 1 to 100 cell edits")
    requested = {}
    for change in changes:
        if (not isinstance(change, dict) or set(change) != {"sheet", "cell", "value"}
                or not isinstance(change["sheet"], str) or not change["sheet"]
                or not isinstance(change["cell"], str) or not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", change["cell"])):
            raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_CHANGE_INVALID", "invalid sheet/cell edit")
        key = (change["sheet"], change["cell"])
        if key in requested:
            raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_CHANGE_INVALID", "duplicate target")
        requested[key] = _numeric_literal(change["value"])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        parts = {info.filename: archive.read(info) for info in archive.infolist()}
        workbook = ET.fromstring(parts["xl/workbook.xml"])
        relationships = ET.fromstring(parts["xl/_rels/workbook.xml.rels"])
        relation_ids = [item.get("Id") for item in relationships]
        if len(relation_ids) != len(set(relation_ids)):
            raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_TARGET_INVALID", "ambiguous workbook relationships")
        targets = {item.get("Id"): item.get("Target") for item in relationships if item.get("TargetMode") != "External"}
        sheets = {}
        for sheet in workbook.findall(S + "sheets/" + S + "sheet"):
            name = sheet.get("name")
            target = targets.get(sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
            if name in sheets or not isinstance(target, str):
                raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_TARGET_INVALID", "ambiguous worksheet")
            part = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not part.startswith("xl/worksheets/") or ".." in part.split("/") or part not in parts:
                raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_TARGET_INVALID", "worksheet unavailable")
            sheets[name] = part
        if len(sheets.values()) != len(set(sheets.values())):
            raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_TARGET_INVALID", "shared worksheet part")
        modified, records, parsed = {}, [], {}
        for (name, address), value in sorted(requested.items()):
            if name not in sheets:
                raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_TARGET_INVALID", "worksheet missing")
            part = sheets[name]
            if part not in parsed:
                parsed[part] = ET.fromstring(parts[part])
            cells = [cell for cell in parsed[part].iter(S + "c") if cell.get("r") == address]
            if len(cells) != 1:
                raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_TARGET_INVALID", "numeric input cell missing/ambiguous")
            cell = cells[0]
            values = cell.findall(S + "v")
            if (cell.get("t", "n") != "n" or cell.find(S + "f") is not None
                    or cell.find(S + "is") is not None or len(values) != 1 or values[0].text is None):
                raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_TARGET_INVALID", "target must be an existing literal numeric input")
            original = values[0].text
            _numeric_literal(original)
            values[0].text = value
            records.append({"sheet": name, "cell": address, "value": value, "original_value": original})
        for part, node in parsed.items():
            modified[part] = ET.tostring(node, encoding="utf-8", xml_declaration=True)
        return parts, modified, records


def prepare_xlsx_counterfactual(source, changes, output_dir):
    """Create a disposable numeric-input variant and a replayable provenance receipt."""
    source = Path(source)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_INPUT_BYTES:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "counterfactual source unavailable")
    data = source.read_bytes()
    _, modified, records = _counterfactual_parts(data, changes)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    prepared, receipt = output / "prepared.xlsx", output / "counterfactual-audit.json"
    if prepared.exists() or receipt.exists():
        raise OfficeRuntimeError("OFFICE_OUTPUT_EXISTS", "counterfactual artifacts are immutable")
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as incoming, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as outgoing:
        for info in incoming.infolist():
            outgoing.writestr(info, modified.get(info.filename, incoming.read(info)))
    digest = hashlib.sha256(data).hexdigest()
    if sha(source) != digest:
        raise OfficeRuntimeError("OFFICE_SOURCE_DRIFT", "counterfactual source changed")
    with prepared.open("xb") as handle:
        handle.write(buffer.getvalue())
    audit = {"schema_version": COUNTERFACTUAL_AUDIT_SCHEMA, "profile": COUNTERFACTUAL_PROFILE,
             "source_sha256": digest, "prepared_sha256": sha(prepared), "source_unchanged": True,
             "changes": records}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    return {"path": str(prepared), "audit_path": str(receipt), "audit": audit}


def verify_xlsx_counterfactual(source, prepared, audit):
    """Verify archived bytes against frozen source, independently of Office availability."""
    source, prepared = Path(source), Path(prepared)
    if (source.is_symlink() or prepared.is_symlink() or not source.is_file() or not prepared.is_file()
            or max(source.stat().st_size, prepared.stat().st_size) > MAX_INPUT_BYTES
            or not isinstance(audit, dict) or audit.get("schema_version") != COUNTERFACTUAL_AUDIT_SCHEMA
            or audit.get("profile") != COUNTERFACTUAL_PROFILE or audit.get("source_unchanged") is not True
            or audit.get("source_sha256") != sha(source) or audit.get("prepared_sha256") != sha(prepared)
            or not isinstance(audit.get("changes"), list)
            or any(not isinstance(row, dict) or set(row) != {"sheet", "cell", "value", "original_value"} for row in audit["changes"])):
        raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_AUDIT_INVALID", "counterfactual binding mismatch")
    edits = [{key: row[key] for key in ("sheet", "cell", "value")} for row in audit["changes"]]
    parts, modified, replayed = _counterfactual_parts(source.read_bytes(), edits)
    if audit["changes"] != replayed:
        raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_AUDIT_INVALID", "declared edits do not match original inputs")
    data = prepared.read_bytes()
    _clean_package(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if set(archive.namelist()) != set(parts):
            raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_AUDIT_INVALID", "package member set changed")
        for name, original in parts.items():
            observed = archive.read(name)
            if name in modified:
                # Check XML semantics rather than ZIP compression or serializer prefixes.
                expected_xml = ET.canonicalize(modified[name], rewrite_prefixes=True)
                actual_xml = ET.canonicalize(observed, rewrite_prefixes=True)
                equal = expected_xml == actual_xml
            else:
                equal = observed == original
            if not equal:
                raise OfficeRuntimeError("OFFICE_COUNTERFACTUAL_AUDIT_INVALID", "undeclared change: " + name)
    return audit


def _scalar_intervention_parts(data, changes, *, numeric=False):
    """Override declared scalar intermediates, preserving a full before image.

    This is a summary-dependency experiment, not a repair or a claim that the
    original marker formula is correct. The caller must verify baseline markers
    and their business role independently before choosing intervention cells.
    """
    _clean_package(data)
    prefix = "OFFICE_NUMERIC_INTERVENTION" if numeric else "OFFICE_MARKER_INTERVENTION"
    invalid = prefix + "_CHANGE_INVALID"
    target_invalid = prefix + "_TARGET_INVALID"
    unsupported = prefix + "_UNSUPPORTED"
    if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
        raise OfficeRuntimeError(invalid, "need 1 to 100 marker edits")
    requested = {}
    for change in changes:
        if (not isinstance(change, dict) or set(change) != {"sheet", "cell", "value"}
                or not isinstance(change["sheet"], str) or not change["sheet"]
                or not isinstance(change["cell"], str)
                or not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]{0,6}", change["cell"])):
            raise OfficeRuntimeError(invalid, "invalid marker sheet/cell edit")
        key = change["sheet"], change["cell"]
        if key in requested:
            raise OfficeRuntimeError(invalid, "duplicate marker target")
        try:
            value = _numeric_literal(change["value"])
        except OfficeRuntimeError as exc:
            raise OfficeRuntimeError(invalid, exc.message) from exc
        if not numeric and value not in {"0", "1"}:
            raise OfficeRuntimeError(invalid, "marker interventions must be zero or one")
        requested[key] = value
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        parts = {info.filename: archive.read(info) for info in archive.infolist()}
        workbook = ET.fromstring(parts["xl/workbook.xml"])
        relationships = ET.fromstring(parts["xl/_rels/workbook.xml.rels"])
        ids = [n.get("Id") for n in relationships]
        if len(ids) != len(set(ids)):
            raise OfficeRuntimeError(target_invalid, "ambiguous workbook relationships")
        targets = {n.get("Id"): n.get("Target") for n in relationships if n.get("TargetMode") != "External"}
        sheets = {}
        for sheet in workbook.findall(S + "sheets/" + S + "sheet"):
            name = sheet.get("name")
            target = targets.get(sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"))
            if name in sheets or not isinstance(target, str):
                raise OfficeRuntimeError(target_invalid, "ambiguous worksheet")
            part = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not part.startswith("xl/worksheets/") or ".." in part.split("/") or part not in parts:
                raise OfficeRuntimeError(target_invalid, "worksheet unavailable")
            sheets[name] = part
        if len(sheets.values()) != len(set(sheets.values())):
            raise OfficeRuntimeError(target_invalid, "shared worksheet part")
        shared = []
        if "xl/sharedStrings.xml" in parts:
            shared = ["".join(t.text or "" for t in si.iter(S + "t"))
                      for si in ET.fromstring(parts["xl/sharedStrings.xml"])]
        parsed, records = {}, []
        for (name, address), value in sorted(requested.items()):
            if name not in sheets:
                raise OfficeRuntimeError(target_invalid, "worksheet missing")
            part = sheets[name]
            if part not in parsed:
                parsed[part] = ET.fromstring(parts[part])
            def position(ref):
                match = re.fullmatch(r"\$?([A-Z]{1,3})\$?([1-9][0-9]{0,6})", ref)
                if match is None:
                    raise OfficeRuntimeError(unsupported, "unsupported formula range")
                col = 0
                for char in match[1]:
                    col = col * 26 + ord(char) - 64
                return int(match[2]), col
            row_number, column_number = position(address)
            for f in parsed[part].iter(S + "f"):
                if f.get("ref"):
                    ends = f.get("ref").split(":")
                    if len(ends) == 1:
                        ends.append(ends[0])
                    if len(ends) != 2:
                        raise OfficeRuntimeError(unsupported, "unsupported formula range")
                    (r1, c1), (r2, c2) = map(position, ends)
                    if r1 <= row_number <= r2 and c1 <= column_number <= c2:
                        raise OfficeRuntimeError(unsupported, "marker belongs to a shared or array formula range")
            cells = [c for c in parsed[part].iter(S + "c") if c.get("r") == address]
            if len(cells) != 1:
                raise OfficeRuntimeError(target_invalid, "marker cell missing or ambiguous")
            cell = cells[0]
            formulas, values = cell.findall(S + "f"), cell.findall(S + "v")
            kind = cell.get("t", "n")
            if (len(formulas) > 1 or len(values) > 1 or cell.get("cm") is not None
                    or cell.get("vm") is not None
                    or any(f.get("t", "normal") != "normal" or f.get("ref") is not None for f in formulas)):
                raise OfficeRuntimeError(unsupported, "shared, array or metadata-backed markers require another intervention profile")
            if formulas:
                if not formulas[0].text or cell.find(S + "is") is not None:
                    raise OfficeRuntimeError(target_invalid, "invalid scalar marker formula")
            else:
                original = values[0].text if values else None
                if kind == "inlineStr":
                    original = "".join(t.text or "" for t in cell.iter(S + "t"))
                elif kind == "s":
                    try:
                        index = int(original)
                        if index < 0:
                            raise ValueError("negative string index")
                        original = shared[index]
                    except (ValueError, TypeError, IndexError) as exc:
                        raise OfficeRuntimeError(target_invalid, "invalid shared marker text") from exc
                elif kind not in {"n", "b", "str"}:
                    raise OfficeRuntimeError(target_invalid, "not a binary marker")
                try:
                    binary = _numeric_literal(original.strip() if isinstance(original, str) else original)
                except OfficeRuntimeError as exc:
                    raise OfficeRuntimeError(target_invalid, "existing marker must be binary") from exc
                if not numeric and binary not in {"0", "1"}:
                    raise OfficeRuntimeError(target_invalid, "existing marker must be binary")
            before_cell = copy.deepcopy(cell)
            before_cell.tail = None
            before = ET.canonicalize(ET.tostring(before_cell, encoding="unicode"), rewrite_prefixes=True)
            if len(before.encode("utf-8")) > 65536:
                raise OfficeRuntimeError(unsupported, "marker before image exceeds supported size")
            records.append({"sheet": name, "cell": address, "value": value, "original_cell": before})
            for child in list(cell):
                if child.tag in {S + "f", S + "v", S + "is"}:
                    cell.remove(child)
            if not numeric and kind in {"s", "str", "inlineStr"}:
                cell.set("t", "inlineStr")
                ET.SubElement(ET.SubElement(cell, S + "is"), S + "t").text = value
            else:
                cell.set("t", "b" if not numeric and kind == "b" else "n")
                ET.SubElement(cell, S + "v").text = value
        modified = {part: ET.tostring(node, encoding="utf-8", xml_declaration=True) for part, node in parsed.items()}
        return parts, modified, records


def _marker_intervention_parts(data, changes):
    return _scalar_intervention_parts(data, changes)


def _numeric_intervention_parts(data, changes):
    return _scalar_intervention_parts(data, changes, numeric=True)


def _prepare_xlsx_intervention(source, changes, output_dir, *, parts_function,
                               audit_schema, profile, receipt_name):
    """Publish immutable experiment bytes and full original-cell provenance."""
    source = Path(source)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_INPUT_BYTES:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "marker intervention source unavailable")
    data = source.read_bytes()
    _, modified, records = parts_function(data, changes)
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    prepared, receipt = output / "prepared.xlsx", output / receipt_name
    if prepared.exists() or receipt.exists():
        raise OfficeRuntimeError("OFFICE_OUTPUT_EXISTS", "marker artifacts are immutable")
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as incoming, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as outgoing:
        for info in incoming.infolist():
            outgoing.writestr(info, modified.get(info.filename, incoming.read(info)))
    digest = hashlib.sha256(data).hexdigest()
    if sha(source) != digest:
        raise OfficeRuntimeError("OFFICE_SOURCE_DRIFT", "marker source changed")
    with prepared.open("xb") as handle:
        handle.write(buffer.getvalue())
    audit = {"schema_version": audit_schema, "profile": profile,
             "source_sha256": digest, "prepared_sha256": sha(prepared), "source_unchanged": True, "changes": records}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    return {"path": str(prepared), "audit_path": str(receipt), "audit": audit}


def _verify_xlsx_intervention(source, prepared, audit, *, parts_function,
                              audit_schema, profile, invalid):
    """Replay declared cells and reject any unbound before image or mutation."""
    source, prepared = Path(source), Path(prepared)
    keys = {"schema_version", "profile", "source_sha256", "prepared_sha256", "source_unchanged", "changes"}
    if (source.is_symlink() or prepared.is_symlink() or not source.is_file() or not prepared.is_file()
            or max(source.stat().st_size, prepared.stat().st_size) > MAX_INPUT_BYTES
            or not isinstance(audit, dict) or set(audit) != keys
            or audit.get("schema_version") != audit_schema
            or audit.get("profile") != profile or audit.get("source_unchanged") is not True
            or audit.get("source_sha256") != sha(source) or audit.get("prepared_sha256") != sha(prepared)
            or not isinstance(audit.get("changes"), list)
            or any(not isinstance(row, dict) or set(row) != {"sheet", "cell", "value", "original_cell"} for row in audit["changes"])):
        raise OfficeRuntimeError(invalid, "marker intervention binding mismatch")
    edits = [{key: row[key] for key in ("sheet", "cell", "value")} for row in audit["changes"]]
    parts, modified, records = parts_function(source.read_bytes(), edits)
    if records != audit["changes"]:
        raise OfficeRuntimeError(invalid, "original marker cells or declared edits differ")
    data = prepared.read_bytes()
    _clean_package(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if set(archive.namelist()) != set(parts):
            raise OfficeRuntimeError(invalid, "marker package member set changed")
        for name, original in parts.items():
            observed = archive.read(name)
            if name in modified:
                equal = ET.canonicalize(modified[name], rewrite_prefixes=True) == ET.canonicalize(observed, rewrite_prefixes=True)
            else:
                equal = original == observed
            if not equal:
                raise OfficeRuntimeError(invalid, "undeclared marker change: " + name)
    return audit


def prepare_xlsx_marker_intervention(source, changes, output_dir):
    """Make an immutable binary-marker experiment; never rewrite the source."""
    return _prepare_xlsx_intervention(source, changes, output_dir,
        parts_function=_marker_intervention_parts, audit_schema=MARKER_INTERVENTION_AUDIT_SCHEMA,
        profile=MARKER_INTERVENTION_PROFILE, receipt_name="marker-intervention-audit.json")


def verify_xlsx_marker_intervention(source, prepared, audit):
    """Replay only declared binary markers, including original formula/cache."""
    return _verify_xlsx_intervention(source, prepared, audit,
        parts_function=_marker_intervention_parts, audit_schema=MARKER_INTERVENTION_AUDIT_SCHEMA,
        profile=MARKER_INTERVENTION_PROFILE, invalid="OFFICE_MARKER_INTERVENTION_AUDIT_INVALID")


def prepare_xlsx_numeric_intervention(source, changes, output_dir):
    """Override numeric intermediates, including ordinary scalar formulas.

    This verifies downstream dependence, not the correctness of the original
    source formula. Rules must independently verify baseline values and select
    legitimate business inputs. The original workbook is never changed.
    """
    return _prepare_xlsx_intervention(source, changes, output_dir,
        parts_function=_numeric_intervention_parts, audit_schema=NUMERIC_INTERVENTION_AUDIT_SCHEMA,
        profile=NUMERIC_INTERVENTION_PROFILE, receipt_name="numeric-intervention-audit.json")


def verify_xlsx_numeric_intervention(source, prepared, audit):
    """Replay a scalar numeric override without requiring an Office engine."""
    return _verify_xlsx_intervention(source, prepared, audit,
        parts_function=_numeric_intervention_parts, audit_schema=NUMERIC_INTERVENTION_AUDIT_SCHEMA,
        profile=NUMERIC_INTERVENTION_PROFILE, invalid="OFFICE_NUMERIC_INTERVENTION_AUDIT_INVALID")


def office_render_lock_digest(lock):
    return hashlib.sha256(json.dumps(lock, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def read_embedded_xlsx(source, part):
    """Read one passive XLSX part from a frozen PPTX without touching files."""
    source = Path(source)
    if source.is_symlink() or not source.is_file() or source.suffix.lower() != ".pptx":
        raise OfficeRuntimeError("OFFICE_EMBEDDED_SOURCE_INVALID", "source must be a regular PPTX")
    if source.stat().st_size > MAX_INPUT_BYTES:
        raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "presentation too large")
    if (not isinstance(part, str) or not part.startswith("ppt/") or not part.lower().endswith(".xlsx")
            or "\\" in part or any(item in {"", ".", ".."} for item in part.split("/"))):
        raise OfficeRuntimeError("OFFICE_EMBEDDED_PART_INVALID", "unsafe embedded part path")
    data = source.read_bytes()
    _inspect_render_package(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        try:
            member = archive.getinfo(part)
        except KeyError as exc:
            raise OfficeRuntimeError("OFFICE_EMBEDDED_PART_INVALID", "embedded XLSX part is missing") from exc
        if member.file_size > MAX_INPUT_BYTES:
            raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "embedded workbook too large")
        workbook = archive.read(member)
    _clean_package(workbook)  # validate; keep original formula caches in this source copy
    if sha(source) != hashlib.sha256(data).hexdigest():
        raise OfficeRuntimeError("OFFICE_SOURCE_DRIFT", "presentation changed while reading embedded data")
    return workbook


def extract_embedded_xlsx(source, part, output_dir):
    """Publish a byte-bound source copy for subsequent trusted recalculation."""
    source = Path(source)
    before = sha(source)
    workbook = read_embedded_xlsx(source, part)
    destination = Path(output_dir).resolve();destination.mkdir(parents=True, exist_ok=True)
    target, receipt = destination / "embedded.xlsx", destination / "embedded-xlsx-audit.json"
    if target.exists() or receipt.exists():
        raise OfficeRuntimeError("OFFICE_OUTPUT_EXISTS", "embedded artifacts are immutable")
    if sha(source) != before:
        raise OfficeRuntimeError("OFFICE_SOURCE_DRIFT", "presentation changed during extraction")
    with target.open("xb") as handle:handle.write(workbook)
    audit = {"schema_version": EMBEDDED_AUDIT_SCHEMA, "source_presentation_sha256": before,
             "part": part, "embedded_sha256": sha(target), "source_unchanged": True}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, sort_keys=True, indent=2);handle.write("\n")
    return {"path": str(target), "audit_path": str(receipt), "audit": audit}


def _font_directory_files(directory):
    path = Path(directory)
    if not path.is_dir() or path.is_symlink():
        raise OfficeRuntimeError("OFFICE_RENDER_FONT_UNAVAILABLE", "font directory unavailable or symbolic link")
    fonts = []
    for font in path.rglob("*"):
        if font.suffix.lower() in {".ttf", ".otf", ".ttc"} and (font.is_file() or font.is_symlink()):
            if font.is_symlink():
                raise OfficeRuntimeError("OFFICE_RENDER_FONT_INVALID", "font directory contains a symbolic link")
            fonts.append(str(font.resolve(strict=True)))
            if len(fonts) > 512:
                raise OfficeRuntimeError("OFFICE_RENDER_FONT_INVALID", "font inventory limit")
    return set(fonts)


def create_office_render_lock(office_lock, font_files, *, font_directories=(), document_format="pptx"):
    """Bind separately supplied font assets without changing the XLSX lock."""
    if document_format not in {"pptx", "docx", "both"}:
        raise OfficeRuntimeError("OFFICE_RENDER_LOCK_INVALID", "unsupported render document format")
    validate_office_lock(office_lock)
    directories = []
    for source in font_directories:
        path = Path(source).expanduser()
        _font_directory_files(path)
        directories.append(str(path.resolve(strict=True)))
    directories = sorted(set(directories))
    paths = {str(Path(path).expanduser()) for path in font_files}
    for directory in directories:
        paths.update(_font_directory_files(directory))
    fonts = []
    for source in sorted(paths):
        path = Path(source).expanduser()
        if path.is_symlink():
            raise OfficeRuntimeError("OFFICE_RENDER_FONT_INVALID", "font must not be a symlink")
        if not path.is_file():
            raise OfficeRuntimeError("OFFICE_RENDER_FONT_UNAVAILABLE", str(path))
        path = path.resolve(strict=True)
        if path.suffix.lower() not in {".ttf", ".otf", ".ttc"} or not 0 < path.stat().st_size <= 128 * 1024 * 1024 or len(fonts) >= 512:
            raise OfficeRuntimeError("OFFICE_RENDER_FONT_INVALID", "invalid font type, size or inventory limit")
        fonts.append({"path": str(path), "sha256": sha(path), "size": path.stat().st_size})
    fonts.sort(key=lambda item: item["path"])
    lock = {"schema_version": MULTI_RENDER_LOCK_SCHEMA if document_format == "both" else RENDER_LOCK_SCHEMA,
            "profile": MULTI_RENDER_PROFILE if document_format == "both" else RENDER_PROFILE if document_format == "pptx" else DOCX_RENDER_PROFILE,
            "office_runtime": dict(office_lock), "fonts": fonts, "font_directories": directories}
    validate_office_render_lock(lock)
    return lock


def validate_office_render_lock(lock, *, require_files=True):
    if (not isinstance(lock, dict) or set(lock) != {"schema_version", "profile", "office_runtime", "fonts", "font_directories"}
            or not ((lock.get("schema_version") == RENDER_LOCK_SCHEMA and lock.get("profile") in (RENDER_PROFILE, DOCX_RENDER_PROFILE))
                    or (lock.get("schema_version") == MULTI_RENDER_LOCK_SCHEMA and lock.get("profile") == MULTI_RENDER_PROFILE))
            or not isinstance(lock.get("fonts"), list) or not 1 <= len(lock["fonts"]) <= 512
            or not isinstance(lock.get("font_directories"), list) or len(lock["font_directories"]) > 16
            or any(not isinstance(path, str) or not Path(path).is_absolute() for path in lock["font_directories"])
            or len(set(lock["font_directories"])) != len(lock["font_directories"])):
        raise OfficeRuntimeError("OFFICE_RENDER_LOCK_INVALID", "render lock requires a bounded explicit font inventory")
    binary = validate_office_lock(lock["office_runtime"], require_executable=require_files)
    seen = set()
    for font in lock["fonts"]:
        if (not isinstance(font, dict) or set(font) != {"path", "sha256", "size"}
                or not isinstance(font.get("path"), str) or not Path(font["path"]).is_absolute()
                or Path(font["path"]).suffix.lower() not in {".ttf", ".otf", ".ttc"}
                or not isinstance(font.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", font["sha256"])
                or type(font.get("size")) is not int or not 0 < font["size"] <= 128 * 1024 * 1024
                or font["path"] in seen):
            raise OfficeRuntimeError("OFFICE_RENDER_LOCK_INVALID", "invalid or duplicate font identity")
        seen.add(font["path"])
        if require_files:
            path = Path(font["path"])
            if not path.is_file() or path.is_symlink():
                raise OfficeRuntimeError("OFFICE_RENDER_FONT_UNAVAILABLE", str(path))
            if path.stat().st_size != font["size"] or sha(path) != font["sha256"]:
                raise OfficeRuntimeError("OFFICE_RENDER_FONT_DRIFT", str(path))
    if require_files:
        for directory in lock["font_directories"]:
            expected = {font["path"] for font in lock["fonts"] if Path(font["path"]).is_relative_to(Path(directory))}
            if _font_directory_files(directory) != expected:
                raise OfficeRuntimeError("OFFICE_RENDER_FONT_DRIFT", "font directory membership changed")
    return binary


def office_render_lock_formats(lock):
    """Return only explicitly authorized formats; no extension-based widening."""
    validate_office_render_lock(lock, require_files=False)
    if lock["schema_version"] == MULTI_RENDER_LOCK_SCHEMA:
        return ("docx", "pptx")
    return ("docx",) if lock["profile"] == DOCX_RENDER_PROFILE else ("pptx",)


def _inspect_render_package(data):
    """Validate a passive PPTX; keep its stored chart and workbook caches intact."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "not a PPTX ZIP") from exc
    embedded_count = 0
    with archive:
        infos = archive.infolist()
        expanded = sum(item.file_size for item in infos)
        names = {item.filename for item in infos}
        if len(infos) > 5000 or expanded > MAX_UNCOMPRESSED_BYTES:
            raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "PPTX package extraction limit")
        if len(names) != len(infos) or not {"[Content_Types].xml", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"} <= names:
            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "duplicate or missing PPTX package parts")
        slide_count = None
        for item in infos:
            name = item.filename
            parts = name.rstrip("/").split("/")
            if item.flag_bits & 1 or name.startswith("/") or "\\" in name or any(part in {"", ".", ".."} for part in parts):
                raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsafe/encrypted PPTX package member")
            lowered = name.lower()
            if any(token in lowered for token in ("vbaproject", "/activex/", "/macrosheets/")):
                raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "active PPTX content is outside passive rendering")
            raw = archive.read(item)
            if name == "[Content_Types].xml":_validate_content_types(raw)
            if lowered.startswith("ppt/embeddings/") and not item.is_dir():
                if not lowered.endswith(".xlsx"):
                    raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "only passive embedded XLSX is supported")
                try:
                    with zipfile.ZipFile(io.BytesIO(raw)) as book:
                        expanded += sum(member.file_size for member in book.infolist())
                except zipfile.BadZipFile as exc:
                    raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "invalid embedded XLSX") from exc
                if expanded > MAX_UNCOMPRESSED_BYTES:
                    raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "PPTX and embedded workbooks exceed combined extraction limit")
                _clean_package(raw)  # validation only: never render the normalized/corrected workbook
                embedded_count += 1
            if lowered.endswith((".xml", ".rels")):
                if len(raw) > 16 * 1024 * 1024 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                    raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsafe or oversized PPTX XML")
                try:
                    node = ET.fromstring(raw)
                except ET.ParseError as exc:
                    raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "malformed PPTX XML") from exc
                if lowered.endswith(".rels") and any(relation.get("TargetMode") == "External"
                        and not relation.get("Type", "").endswith("/hyperlink") for relation in node):
                    raise OfficeRuntimeError("OFFICE_EXTERNAL_DATA_UNSUPPORTED", "linked data/assets are outside passive offline rendering")
                if lowered.endswith(".rels"):
                    owner_dir = posixpath.dirname(posixpath.dirname(name))
                    for relation in node:
                        if relation.get("Type", "").endswith("/hyperlink"):
                            continue  # passive PDF export does not click hyperlinks
                        target = unquote(relation.get("Target", ""))
                        uri = urlsplit(target)
                        resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(owner_dir, target))
                        if (not target or "\\" in target or uri.scheme or uri.netloc or uri.query or uri.fragment
                                or resolved == ".." or resolved.startswith("../") or resolved not in names):
                            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "PPTX relationship escapes or misses its package part")
                if lowered == "[content_types].xml" and b"macroenabled" in raw.lower():
                    raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "macro-enabled presentation content type")
                if name == "ppt/presentation.xml":
                    if node.tag != "{http://schemas.openxmlformats.org/presentationml/2006/main}presentation":
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsupported presentation namespace")
                    slide_count = len(node.findall("{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst/{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"))
        if not slide_count:
            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "presentation has no declared slides")
    return {"source_slide_count": slide_count, "embedded_xlsx_validated": embedded_count}


def _inspect_docx_render_package(data):
    """Inspect a passive Word package; do not modify its fields or stored text."""
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    relns = "{http://schemas.openxmlformats.org/package/2006/relationships}"
    reltype = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "not a DOCX ZIP") from exc
    with archive:
        infos = archive.infolist()
        names = {item.filename for item in infos}
        if len(infos) > 5000 or sum(item.file_size for item in infos) > MAX_UNCOMPRESSED_BYTES:
            raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "DOCX package extraction limit")
        if len(names) != len(infos) or not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= names:
            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "duplicate or missing DOCX package parts")
        document = None
        main_targets = []
        active_fields = {"DDE", "DDEAUTO", "INCLUDETEXT", "INCLUDEPICTURE", "LINK", "DATABASE", "IMPORT", "MACROBUTTON"}
        def check_instruction(text):
            command = text.strip().split(None, 1)
            if command and command[0].upper() in active_fields:
                raise OfficeRuntimeError("OFFICE_EXTERNAL_DATA_UNSUPPORTED", "active or linked Word field is outside passive rendering")
        for item in infos:
            name = item.filename
            parts = name.rstrip("/").split("/")
            if item.flag_bits & 1 or name.startswith("/") or "\\" in name or any(part in {"", ".", ".."} for part in parts):
                raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsafe/encrypted DOCX package member")
            lowered = name.lower()
            if any(token in lowered for token in ("vbaproject", "/activex/", "/embeddings/", "/afchunk", "customui/")):
                raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "active/embedded Word content is outside passive rendering")
            raw = archive.read(item)
            if name == "[Content_Types].xml":
                _validate_content_types(raw)
            if not lowered.endswith((".xml", ".rels")):
                continue
            checked = raw.replace(b"\x00", b"").upper()
            if len(raw) > 16 * 1024 * 1024 or b"<!DOCTYPE" in checked or b"<!ENTITY" in checked:
                raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsafe or oversized DOCX XML")
            try:
                node = ET.fromstring(raw)
            except ET.ParseError as exc:
                raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "malformed DOCX XML") from exc
            if name == "[Content_Types].xml" and any("macroenabled" in child.get("ContentType", "").lower() for child in node):
                raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "macro-enabled Word content type")
            if lowered.endswith(".rels"):
                if node.tag != relns + "Relationships":
                    raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsupported Word relationship root")
                seen = set()
                owner_dir = posixpath.dirname(posixpath.dirname(name))
                for relation in node:
                    identity = relation.get("Id")
                    if relation.tag != relns + "Relationship" or not identity or identity in seen:
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "missing or ambiguous Word relationship ID")
                    seen.add(identity)
                    kind, mode = relation.get("Type", ""), relation.get("TargetMode", "Internal")
                    if mode not in {"Internal", "External"}:
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsupported Word relationship mode")
                    if kind.endswith(("/oleObject", "/package", "/aFChunk", "/control")):
                        raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "embedded Word relationship is outside passive rendering")
                    if kind == reltype + "hyperlink":
                        continue  # PDF export does not activate hyperlink targets.
                    if mode == "External":
                        raise OfficeRuntimeError("OFFICE_EXTERNAL_DATA_UNSUPPORTED", "linked Word data/assets are outside passive rendering")
                    target = unquote(relation.get("Target", ""))
                    try:
                        uri = urlsplit(target)
                    except ValueError as exc:
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "invalid Word relationship URI") from exc
                    resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(owner_dir, target))
                    if (not target or "\\" in target or uri.scheme or uri.netloc or uri.query or uri.fragment
                            or resolved == ".." or resolved.startswith("../") or resolved not in names):
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "Word relationship escapes or misses its package part")
                    if name == "_rels/.rels" and kind == reltype + "officeDocument":
                        main_targets.append(resolved)
            instructions = []
            for element in node.iter():
                if element.tag in {w + "altChunk", w + "object", w + "control", w + "subDoc"}:
                    raise OfficeRuntimeError("OFFICE_ACTIVE_CONTENT_UNSUPPORTED", "active Word element is outside passive rendering")
                if element.tag == w + "fldSimple":
                    check_instruction(element.get(w + "instr", ""))
                elif element.tag == w + "fldChar":
                    kind = element.get(w + "fldCharType")
                    if kind == "begin":
                        instructions.append("")
                    elif kind in {"separate", "end"} and instructions:
                        check_instruction(instructions[-1])
                        if kind == "end":
                            instructions.pop()
                elif element.tag == w + "instrText":
                    if not instructions:
                        # Unbalanced field fragments cannot be interpreted safely.
                        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unbalanced Word field instruction")
                    instructions[-1] += element.text or ""
            for instruction in instructions:
                check_instruction(instruction)
            if name == "word/document.xml":
                document = node
        if main_targets != ["word/document.xml"] or document is None or document.tag != w + "document":
            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "unsupported Word main document relationship/namespace")
        body = document.find(w + "body")
        if body is None:
            raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "Word document body missing")
        return {"source_format": "docx", "source_body_paragraph_count": sum(1 for _ in body.iter(w + "p")),
                "source_body_table_count": sum(1 for _ in body.iter(w + "tbl")),
                "source_section_count": sum(1 for _ in body.iter(w + "sectPr"))}


def render_pptx_pdf(source, render_lock, output_dir, *, timeout_seconds=60):
    """Render a byte-identical disposable PPTX with frozen engine/font identities."""
    return _render_office_pdf(source, render_lock, output_dir, document_format="pptx", timeout_seconds=timeout_seconds)


def render_docx_pdf(source, render_lock, output_dir, *, timeout_seconds=60):
    """Render passive Word text/tables/notes with the explicit DOCX font lock."""
    return _render_office_pdf(source, render_lock, output_dir, document_format="docx", timeout_seconds=timeout_seconds)


def _render_office_pdf(source, render_lock, output_dir, *, document_format, timeout_seconds):
    word = document_format == "docx"
    profile_name = DOCX_RENDER_PROFILE if word else RENDER_PROFILE
    export_filter = DOCX_RENDER_FILTER if word else RENDER_FILTER
    source_name = "document.docx" if word else "presentation.pptx"
    pdf_name = "document.pdf" if word else "presentation.pdf"
    source = Path(source)
    if source.is_symlink() or source.suffix.lower() != "." + document_format:
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "Office source must be a regular file of the declared format")
    source = source.resolve(strict=True)
    if not source.is_file() or source.stat().st_size > MAX_INPUT_BYTES:
        raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "presentation unavailable or too large")
    binary = validate_office_render_lock(render_lock)
    if document_format not in office_render_lock_formats(render_lock):
        raise OfficeRuntimeError("OFFICE_RENDER_PROFILE_MISMATCH", "render lock does not authorize this document format")
    data = source.read_bytes()
    if len(data) > MAX_INPUT_BYTES:
        raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "Office input grew beyond rendering limit")
    original_sha = hashlib.sha256(data).hexdigest()
    source_info = _inspect_docx_render_package(data) if word else _inspect_render_package(data)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    target, receipt = destination / "rendered.pdf", destination / "render-audit.json"
    if target.exists() or receipt.exists():
        raise OfficeRuntimeError("OFFICE_OUTPUT_EXISTS", "derived artifacts are immutable; choose a new directory")
    with _temporary() as temporary:
        root = Path(temporary)
        incoming, outgoing, profile, fonts = (root / name for name in ("input", "output", "profile", "fonts"))
        for folder in (incoming, outgoing, profile, fonts):
            folder.mkdir()
        (incoming / source_name).write_bytes(data)
        for index, font in enumerate(render_lock["fonts"]):
            copied = fonts / (f"font-{index:02d}" + Path(font["path"]).suffix.lower())
            shutil.copyfile(font["path"], copied)
            if sha(copied) != font["sha256"]:
                raise OfficeRuntimeError("OFFICE_RENDER_FONT_DRIFT", "font changed while copied")
        config = ET.Element("fontconfig")
        ET.SubElement(config, "dir").text = str(fonts)
        ET.SubElement(config, "cachedir").text = str(root / "font-cache")
        fontconfig = root / "fonts.conf"
        fontconfig.write_bytes(ET.tostring(config, encoding="utf-8", xml_declaration=True))
        env = _environment(root)
        env.update(FONTCONFIG_FILE=str(fontconfig), SAL_FONTPATH_PRIVATE=str(fonts))
        export = "pdf:" + ("writer_pdf_Export:" if word else "impress_pdf_Export:") + json.dumps(export_filter, separators=(",", ":"))
        command = [str(binary), "-env:UserInstallation=" + profile.as_uri(), "--headless", "--invisible", "--norestore",
                   "--convert-to", export, "--outdir", str(outgoing), str(incoming / source_name)]
        try:
            result = subprocess.run(command, env=env, cwd=root, capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise OfficeRuntimeError("OFFICE_RENDER_TIMEOUT", "trusted Office rendering did not complete") from exc
        converted = outgoing / pdf_name
        if result.returncode or not converted.is_file():
            raise OfficeRuntimeError("OFFICE_RENDER_FAILED", result.stderr.decode("utf-8", errors="replace")[-1500:])
        derived = converted.read_bytes()
        if not derived.startswith(b"%PDF-") or b"%%EOF" not in derived[-1024:]:
            raise OfficeRuntimeError("OFFICE_RENDER_FAILED", "engine did not produce a complete PDF envelope")
        stdout = result.stdout.decode("utf-8", errors="replace")[-4000:]
        stderr = result.stderr.decode("utf-8", errors="replace")[-4000:]
    validate_office_render_lock(render_lock)
    if sha(source) != original_sha:
        raise OfficeRuntimeError("OFFICE_SOURCE_DRIFT", "source Office document changed during rendering")
    with target.open("xb") as handle:
        handle.write(derived)
    audit = {"schema_version": DOCX_RENDER_AUDIT_SCHEMA if word else RENDER_AUDIT_SCHEMA, "profile": profile_name,
             "engine_version": render_lock["office_runtime"]["engine_version"],
             "executable_sha256": render_lock["office_runtime"]["executable_sha256"],
             "render_lock_sha256": office_render_lock_digest(render_lock),
             "font_assets": [{key: font[key] for key in ("sha256", "size")} for font in render_lock["fonts"]],
             "source_sha256": original_sha, "derived_sha256": sha(target), "source_unchanged": True,
             "environment_profile": "isolated-fontconfig/v1", "export_filter": export_filter,
             **source_info, "stdout": stdout, "stderr": stderr,
             "limit": "PDF conversion only; page count, visual fit, font usage, editability and semantic correctness need independent checks."}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, sort_keys=True, indent=2);handle.write("\n")
    return {"path": str(target), "audit_path": str(receipt), "audit": audit}
