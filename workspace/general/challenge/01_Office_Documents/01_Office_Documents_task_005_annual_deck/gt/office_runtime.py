"""Frozen LibreOffice operations on disposable copies: XLSX math and PPTX PDF.

This helper is intentionally standalone so an identical, hashed copy can live
in a dataset's private scoring materials. It never writes the source workbook.
"""
from __future__ import annotations

import hashlib
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
RENDER_AUDIT_SCHEMA = "wildclawbench.office-pptx-render/v1"
RENDER_PROFILE = "offline-pptx-to-pdf-with-fonts/v1"
EMBEDDED_AUDIT_SCHEMA = "wildclawbench.office-embedded-xlsx/v1"
RENDER_FILTER = {"ExportHiddenSlides": {"type": "boolean", "value": "true"},
                 "ExportNotesPages": {"type": "boolean", "value": "false"},
                 "ExportOnlyNotesPages": {"type": "boolean", "value": "false"}}


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


def create_office_render_lock(office_lock, font_files, *, font_directories=()):
    """Bind separately supplied font assets without changing the XLSX lock."""
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
    lock = {"schema_version": RENDER_LOCK_SCHEMA, "profile": RENDER_PROFILE,
            "office_runtime": dict(office_lock), "fonts": fonts, "font_directories": directories}
    validate_office_render_lock(lock)
    return lock


def validate_office_render_lock(lock, *, require_files=True):
    if (not isinstance(lock, dict) or set(lock) != {"schema_version", "profile", "office_runtime", "fonts", "font_directories"}
            or lock.get("schema_version") != RENDER_LOCK_SCHEMA or lock.get("profile") != RENDER_PROFILE
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


def render_pptx_pdf(source, render_lock, output_dir, *, timeout_seconds=60):
    """Render a byte-identical disposable PPTX with frozen engine/font identities."""
    source = Path(source)
    if source.is_symlink() or source.suffix.lower() != ".pptx":
        raise OfficeRuntimeError("OFFICE_INPUT_INVALID", "PPTX source must be a regular non-symlink file")
    source = source.resolve(strict=True)
    if not source.is_file() or source.stat().st_size > MAX_INPUT_BYTES:
        raise OfficeRuntimeError("OFFICE_INPUT_LIMIT", "presentation unavailable or too large")
    binary = validate_office_render_lock(render_lock)
    data = source.read_bytes()
    original_sha = hashlib.sha256(data).hexdigest()
    source_info = _inspect_render_package(data)
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
        (incoming / "presentation.pptx").write_bytes(data)
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
        export = "pdf:impress_pdf_Export:" + json.dumps(RENDER_FILTER, separators=(",", ":"))
        command = [str(binary), "-env:UserInstallation=" + profile.as_uri(), "--headless", "--invisible", "--norestore",
                   "--convert-to", export, "--outdir", str(outgoing), str(incoming / "presentation.pptx")]
        try:
            result = subprocess.run(command, env=env, cwd=root, capture_output=True, timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise OfficeRuntimeError("OFFICE_RENDER_TIMEOUT", "trusted PPTX rendering did not complete") from exc
        converted = outgoing / "presentation.pdf"
        if result.returncode or not converted.is_file():
            raise OfficeRuntimeError("OFFICE_RENDER_FAILED", result.stderr.decode("utf-8", errors="replace")[-1500:])
        derived = converted.read_bytes()
        if not derived.startswith(b"%PDF-") or b"%%EOF" not in derived[-1024:]:
            raise OfficeRuntimeError("OFFICE_RENDER_FAILED", "engine did not produce a complete PDF envelope")
        stdout = result.stdout.decode("utf-8", errors="replace")[-4000:]
        stderr = result.stderr.decode("utf-8", errors="replace")[-4000:]
    validate_office_render_lock(render_lock)
    if sha(source) != original_sha:
        raise OfficeRuntimeError("OFFICE_SOURCE_DRIFT", "source presentation changed during rendering")
    with target.open("xb") as handle:
        handle.write(derived)
    audit = {"schema_version": RENDER_AUDIT_SCHEMA, "profile": RENDER_PROFILE,
             "engine_version": render_lock["office_runtime"]["engine_version"],
             "executable_sha256": render_lock["office_runtime"]["executable_sha256"],
             "render_lock_sha256": office_render_lock_digest(render_lock),
             "font_assets": [{key: font[key] for key in ("sha256", "size")} for font in render_lock["fonts"]],
             "source_sha256": original_sha, "derived_sha256": sha(target), "source_unchanged": True,
             "environment_profile": "isolated-fontconfig/v1", "export_filter": RENDER_FILTER,
             **source_info, "stdout": stdout, "stderr": stderr,
             "limit": "PDF conversion only; page count, visual fit, font usage, editability and semantic correctness need independent checks."}
    with receipt.open("x", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, sort_keys=True, indent=2);handle.write("\n")
    return {"path": str(target), "audit_path": str(receipt), "audit": audit}
