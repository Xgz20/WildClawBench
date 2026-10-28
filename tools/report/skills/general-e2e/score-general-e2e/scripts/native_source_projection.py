"""Offline, bounded native research-source projection; no Office or formulas run.

The profile promises complete extraction of its declared text/stored-cell scope,
not complete visual interpretation, fresh formula results, or semantic support.
"""
from __future__ import annotations

import hashlib
import binascii
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import stat
import struct
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile
import zlib

import research_sources as legacy

PROFILE = "public-native-text-cells/v1"
SCHEMA = "wildclawbench.research-source-text/v2"
DEFAULT_LIMITS = {
    "max_projection_chars": 4_000_000, "max_native_records": 100_000,
    "max_zip_members": 5000, "max_uncompressed_bytes": 100 * 1024 * 1024,
    "max_part_bytes": 16 * 1024 * 1024, "max_compression_ratio": 1000,
    "max_xml_nodes": 300_000, "max_xml_depth": 128, "max_sheets": 256,
}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/pdf": "pdf",
    "application/msword": "unsupported", "application/vnd.ms-excel": "unsupported",
    "application/vnd.ms-excel.sheet.macroenabled.12": "unsupported",
    "application/vnd.ms-word.document.macroenabled.12": "unsupported",
}
MAIN_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
}


def error(code: str, detail: str):
    raise legacy.ResearchSourceError("RESEARCH_SOURCE_" + code, detail)


def _xml(raw: bytes, spec: dict) -> ET.Element:
    try:
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    except UnicodeError as exc:
        error("NATIVE_INVALID", "OOXML XML encoding unsupported: " + str(exc))
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        error("NATIVE_INVALID", "DTD/entity declarations forbidden")
    parser = ET.XMLPullParser(events=("start", "end"))
    depth = count = 0
    try:
        for index in range(0, len(text), 16384):
            parser.feed(text[index:index+16384])
            for event, _ in parser.read_events():
                if event == "start":
                    depth += 1; count += 1
                    if depth > spec["max_xml_depth"] or count > spec["max_xml_nodes"]:
                        error("NATIVE_LIMIT", "XML depth/node limit")
                else:
                    depth -= 1
        parser.close()
        return ET.fromstring(text)
    except ET.ParseError as exc:
        error("NATIVE_INVALID", "malformed OOXML XML: " + str(exc))


def _part_bytes(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int,
                spans: list[tuple[int,int]], source_bytes: int) -> bytes:
    """Bound actual deflate output, independently of declared uncompressed size.

    ZipExtFile deliberately honors the central directory's size. Reading the
    compressed stream with an output cap also detects forged small-size entries.
    """
    handle = archive.fp
    if handle is None or info.header_offset < 0 or info.compress_size < 0:
        error("NATIVE_INVALID", "ZIP member offset")
    handle.seek(info.header_offset)
    header = handle.read(30)
    if len(header) != 30 or header[:4] != b"PK\x03\x04":
        error("NATIVE_INVALID", "ZIP local header")
    flags, method = struct.unpack_from("<HH",header,6)
    name_length, extra_length = struct.unpack_from("<HH",header,26)
    name_bytes = handle.read(name_length)
    name = name_bytes.decode("utf-8" if flags & 0x800 else "cp437")
    if name != info.orig_filename or flags != info.flag_bits or method != info.compress_type:
        error("NATIVE_INVALID", "ZIP local/central header mismatch")
    start = info.header_offset
    payload = start + 30 + name_length + extra_length
    end = payload + info.compress_size
    if end > source_bytes or any(start < b and a < end for a,b in spans):
        error("NATIVE_INVALID", "overlapping/outside ZIP member")
    spans.append((start,end));handle.seek(payload)
    compressed = handle.read(info.compress_size)
    if len(compressed) != info.compress_size:
        error("NATIVE_INVALID", "truncated ZIP member")
    if method == zipfile.ZIP_STORED:
        raw = compressed
    else:
        decoder = zlib.decompressobj(-zlib.MAX_WBITS)
        raw = decoder.decompress(compressed,limit+1)
        if len(raw) > limit or decoder.unconsumed_tail:
            error("NATIVE_LIMIT", "actual deflate expansion limit")
        if not decoder.eof or decoder.unused_data:
            error("NATIVE_INVALID", "deflate stream boundary")
    if len(raw)>limit:
        error("NATIVE_LIMIT", "actual ZIP member limit")
    if len(raw)!=info.file_size or (binascii.crc32(raw) & 0xffffffff)!=info.CRC:
        error("NATIVE_INVALID", "ZIP expanded size/CRC mismatch")
    return raw


def _package(path: Path, spec: dict) -> tuple[str, dict, dict[str, ET.Element]]:
    """Read bounded parts in memory; never extract or follow a relationship."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > spec["max_zip_members"]:
                error("NATIVE_LIMIT", "ZIP member count")
            seen, total, parts, xml, spans = set(), 0, [], {}, []
            for info in infos:
                name = info.filename
                decoded = unquote(name)
                tokens = decoded.rstrip("/").split("/")
                mode = (info.external_attr >> 16) & 0xFFFF
                if (not name or "\0" in name or "\\" in decoded or decoded.startswith("/")
                        or any(p in {"", ".", ".."} for p in tokens)
                        or re.match(r"^[A-Za-z]:", decoded) or decoded.casefold() in seen
                        or info.flag_bits & 1 or stat.S_ISLNK(mode)
                        or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                    error("NATIVE_INVALID", "unsafe/duplicate/encrypted ZIP member")
                seen.add(decoded.casefold())
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    error("NATIVE_UNSUPPORTED", "ZIP compression method")
                if (info.file_size > spec["max_part_bytes"]
                        or info.file_size > max(1, info.compress_size) * spec["max_compression_ratio"]):
                    error("NATIVE_LIMIT", "ZIP part size/compression ratio")
                raw = _part_bytes(archive,info,min(spec["max_part_bytes"],spec["max_uncompressed_bytes"]-total),
                                  spans,path.stat().st_size)
                total += len(raw)
                parts.append({"part": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
                if name.endswith((".xml", ".rels")):
                    xml[name] = _xml(raw, spec)
            names = {p["part"] for p in parts}
            if "[Content_Types].xml" not in xml or "_rels/.rels" not in xml:
                error("NATIVE_INVALID", "OOXML package identity missing")
            content = xml["[Content_Types].xml"]
            if content.tag != CT + "Types":
                error("NATIVE_UNSUPPORTED", "OOXML namespace/content types")
            overrides = {}
            for node in content.findall(CT + "Override"):
                part = node.get("PartName", "").lstrip("/")
                if not part or part in overrides:
                    error("NATIVE_INVALID", "duplicate/invalid content-type override")
                overrides[part] = node.get("ContentType", "")
            active = any(token in p.casefold() for p in names for token in
                         ("vbaproject", "activex/", "macrosheets/")) or any(
                         any(token in t.casefold() for token in ("macro", "vba", "activex")) for t in overrides.values())
            if active:
                error("NATIVE_UNSUPPORTED", "macro/ActiveX content is not supported")
            kind = next((k for k, main in (("docx", "word/document.xml"), ("xlsx", "xl/workbook.xml"))
                         if main in names and overrides.get(main) == MAIN_TYPES[k]), None)
            if kind is None or ("word/document.xml" in names and "xl/workbook.xml" in names):
                error("NATIVE_UNSUPPORTED", "not a supported DOCX/XLSX package")
            rels = []
            main_targets = []
            for part, root in xml.items():
                if not part.endswith(".rels"):
                    continue
                if root.tag != PKG_REL + "Relationships":
                    error("NATIVE_INVALID", "relationship namespace")
                owner = "" if part == "_rels/.rels" else posixpath.join(
                    posixpath.dirname(posixpath.dirname(part)), posixpath.basename(part)[:-5])
                ids = set()
                for node in root:
                    identity, target = node.get("Id"), node.get("Target", "")
                    if not identity or identity in ids or not target:
                        error("NATIVE_INVALID", "ambiguous relationship ID/target")
                    ids.add(identity)
                    external = node.get("TargetMode") == "External"
                    item = {"relationship_part": part, "id": identity, "type": node.get("Type", ""),
                            "target": target, "status": "external_not_followed" if external else "internal"}
                    if not external:
                        target = unquote(target); uri = urlsplit(target)
                        if ("\\" in target or uri.scheme or uri.netloc or uri.query or "\0" in target):
                            error("NATIVE_INVALID", "unsafe relationship target")
                        resolved = posixpath.normpath(uri.path.lstrip("/") if uri.path.startswith("/") else
                                                     posixpath.join(posixpath.dirname(owner), uri.path))
                        if not uri.path and uri.fragment:
                            resolved = owner
                        if resolved.startswith("../") or resolved == ".." or resolved not in names:
                            error("NATIVE_INVALID", "missing/escaping relationship part")
                        item["resolved_part"] = resolved
                        if part == "_rels/.rels" and item["type"].endswith("/officeDocument"):
                            main_targets.append(resolved)
                    rels.append(item)
            expected = "word/document.xml" if kind == "docx" else "xl/workbook.xml"
            if main_targets != [expected]:
                error("NATIVE_INVALID", "package root officeDocument binding")
            return kind, {"parts": parts, "relationships": rels,
                          "excluded_objects": [n for n in sorted(names) if any(t in n.casefold() for t in
                                                ("/media/", "/embeddings/", "externallinks/", "connections.xml"))]}, xml
    except legacy.ResearchSourceError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError, NotImplementedError, zlib.error, UnicodeError, struct.error) as exc:
        error("NATIVE_INVALID", str(exc))


def identify(path: Path, media_type: str, spec: dict, *, urls: tuple = ()) -> str:
    with path.open("rb") as handle:
        head = handle.read(8)
    media = media_type.lower().split(";", 1)[0]
    if head == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        error("NATIVE_UNSUPPORTED", "OLE/BIFF .xls and legacy .doc are unsupported")
    if head.startswith(b"PK"):
        kind, _, _ = _package(path, spec)
    elif head.startswith(b"%PDF-"):
        kind = "pdf"
    else:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            error("EXTRACTION_UNSUPPORTED", "not PDF, supported OOXML or UTF-8 text")
        kind = "html" if "html" in media or re.match(r"\s*(?:<!doctype\s+html|<html)", text, re.I) else "utf8"
    declared = MIMES.get(media)
    if declared == "unsupported":
        error("NATIVE_UNSUPPORTED", "legacy or macro-enabled MIME: " + media)
    if declared is not None and declared != kind:
        error("FORMAT_MISMATCH", "media type disagrees with original bytes")
    if kind in {"docx", "xlsx"} and (media.startswith("text/") or media in {"application/json", "application/xml"}):
        error("FORMAT_MISMATCH", "native binary declared as text")
    for value in (*urls, path.name):
        suffix = PurePosixPath(unquote(urlsplit(str(value)).path)).suffix.lower()
        expected = {".docx":"docx", ".xlsx":"xlsx", ".pdf":"pdf", ".xls":"unsupported", ".doc":"unsupported"}.get(suffix)
        if expected == "unsupported":
            error("NATIVE_UNSUPPORTED", suffix)
        if expected is not None and kind != expected:
            error("FORMAT_MISMATCH", "extension disagrees with original bytes")
    if kind not in spec["allowed_formats"]:
        error("FORMAT_UNSUPPORTED", kind)
    return kind


def _core():
    vendor = Path(__file__).resolve().parents[1] / "vendor/e2e-shared"
    if vendor.is_dir() and str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    try:
        from wildclawbench_grading_core import native_text
    except ImportError as exc:
        error("EXTRACTOR_UNAVAILABLE", str(exc))
    return native_text


def _native(path: Path, spec: dict, kind: str) -> tuple[list, dict, dict, list]:
    _, coverage, xml = _package(path, spec)
    core = _core()
    try:
        view = core.extract_native_text(path, max_chars=spec["max_projection_chars"])
    except core.NativeTextError as exc:
        code = "NATIVE_LIMIT" if exc.code == "NATIVE_TEXT_LIMIT" else "NATIVE_INVALID"
        error(code, str(exc))
    if (view["truncated"] or view["record_offset"] != 0
            or view["selected_record_count"] != view["record_count"]
            or view["record_count"] > spec["max_native_records"]):
        error("NATIVE_LIMIT", "incomplete native records")
    raw_records = [json.loads(line) for line in view["text"].splitlines()]
    if len(raw_records) != view["record_count"]:
        error("NATIVE_INVALID", "native record count")
    part_shas = {p["part"]:p["sha256"] for p in coverage["parts"]}
    records = []
    sheet_parts, cell_lineage = {}, {}
    if kind == "xlsx":
        book = xml["xl/workbook.xml"]
        sheets = book.find(S + "sheets")
        if sheets is None or len(sheets) > spec["max_sheets"]:
            error("NATIVE_LIMIT", "sheet count")
        rels = {r["id"]:r for r in coverage["relationships"] if r["relationship_part"] == "xl/_rels/workbook.xml.rels"}
        for sheet in sheets:
            rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            relation = rels.get(rid)
            if not relation or relation["status"] != "internal":
                error("NATIVE_UNSUPPORTED", "external or missing worksheet")
            name, part = sheet.get("name"), relation["resolved_part"]
            if not name or name in sheet_parts:
                error("NATIVE_INVALID", "ambiguous sheet name")
            root = xml.get(part)
            if root is None or root.tag != S + "worksheet":
                error("NATIVE_UNSUPPORTED", "worksheet namespace/type")
            addresses, physical_cells = set(), {}
            for row_index, physical_row in enumerate(root.iter(S + "row"), 1):
                for cell_index, cell in enumerate(physical_row.findall(S + "c"), 1):
                    physical_cells[id(cell)] = {"xml_row_index":row_index, "declared_row":physical_row.get("r"),
                                                "xml_cell_index":cell_index}
            if len(physical_cells) > spec["max_native_records"]:
                error("NATIVE_LIMIT", "worksheet cell count")
            cell_lineage[name] = {}
            for cell in root.iter(S + "c"):
                address = cell.get("r", "")
                match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", address)
                col = 0
                for char in match[1] if match else "":
                    col = col * 26 + ord(char) - 64
                if not match or int(match[2]) > 1048576 or col > 16384 or address in addresses:
                    error("NATIVE_INVALID", "invalid/duplicate worksheet cell")
                lineage = physical_cells.get(id(cell))
                if lineage is None or lineage["declared_row"] not in {None,match[2]}:
                    error("NATIVE_INVALID", "cell outside or inconsistent with its XML row")
                cell_lineage[name][address] = lineage
                addresses.add(address)
            sheet_parts[name] = {"part": part, "sheet_id": sheet.get("sheetId"), "relationship_id":rid,
                                 "state":sheet.get("state", "visible")}
        coverage["worksheets"] = sheet_parts
        coverage["workbook_observations"] = {
            "defined_names": [dict(n.attrib, stored_text=n.text or "") for n in book.iter(S + "definedName")],
            "calc_properties": dict(book.find(S + "calcPr").attrib) if book.find(S + "calcPr") is not None else {},
        }
        coverage["worksheet_observations"] = {
            name:{"merges":[n.get("ref") for n in xml[d["part"]].iter(S + "mergeCell")],
                  "rows":[dict(n.attrib) for n in xml[d["part"]].iter(S + "row")],
                  "columns":[dict(n.attrib) for n in xml[d["part"]].iter(S + "col")]}
            for name,d in sheet_parts.items()}
    for index, row in enumerate(raw_records, 1):
        native_locator = row["locator"]
        if kind == "xlsx":
            if native_locator.startswith("sheet:") and "type" not in row:
                name = native_locator[6:]
                locator = {"sheet":name, **sheet_parts[name]}
                role, text = "worksheet", ""
            else:
                name, address = native_locator.rsplit("!", 1)
                locator = {"sheet":name, "cell":address, **sheet_parts[name], **cell_lineage[name][address]}
                role = "stored_formula_cache" if "formula" in row else "stored_cell_value"
                value = row.get("value")
                text = "" if value is None else str(value) if not isinstance(value, bool) else str(value).lower()
                row = {**row, "value_role":role, "cache_freshness":"not_verified" if "formula" in row else "not_applicable"}
        else:
            part = row.get("part") or next((n for n in xml if native_locator.startswith(n + "/")), "word/document.xml")
            locator = {"part":part, "node":native_locator}
            role, text = row.get("context", "word_text"), row.get("text", "")
        part = locator["part"]
        locator["part_sha256"] = part_shas[part]
        records.append({"id":f"record-{index:06d}", "locator":locator, "role":role,
                        "text":text, "native":row})
    engine = {**view["engine"], "module_sha256":legacy.sha(Path(core.__file__)),
              "projector_sha256":legacy.sha(Path(__file__)), "profile":PROFILE}
    limits = [*view["limitations"], "Source formula caches are stored observations only; never recalculated or certified current.",
              "Logical OOXML nodes/cells are not rendered physical pages; external relationships are not followed."]
    return records, coverage, engine, limits


def project(path: Path, media_type: str, spec: dict) -> dict:
    kind = identify(path, media_type, spec)
    if kind in {"docx", "xlsx"}:
        records, coverage, engine, limitations = _native(path, spec, kind)
        raw_metadata = {}
    else:
        old = legacy.project(path, media_type)
        records = [{**r, "id":f"record-{i:06d}", "role":"source_text"} for i,r in enumerate(old["records"],1)]
        coverage, engine, limitations = {}, {**old["engine"], "projector_sha256":legacy.sha(Path(__file__))}, ["Text only; no image/layout interpretation."]
        raw_metadata = old["raw_metadata"]
    result = {"schema_version":SCHEMA, "profile":PROFILE, "format":kind,
              "source_sha256":legacy.sha(path), "complete":True,
              "complete_scope":"declared text and stored-cell profile; not visual or semantic completeness",
              "record_count":len(records), "records":records, "coverage":coverage,
              "engine":engine, "limitations":limitations, "raw_metadata":raw_metadata}
    if len(legacy.encoded(result)) > spec["max_projection_chars"] or len(records) > spec["max_native_records"]:
        error("NATIVE_LIMIT", "projection budget; no silent truncation")
    if not records or not any(r["text"].strip() or r.get("native", {}).get("formula") is not None for r in records):
        error("EXTRACTION_FAILED", "no extractable text/stored cells")
    validate_projection(result, path, spec)
    return result


def validate_projection(projection: dict, body: Path, spec: dict) -> None:
    """Static shape/content binding also usable on archive hosts without parsers."""
    rows = projection.get("records")
    if (projection.get("schema_version") != SCHEMA or projection.get("profile") != spec["projection_profile"]
            or projection.get("source_sha256") != legacy.sha(body) or projection.get("complete") is not True
            or projection.get("format") not in spec["allowed_formats"]
            or not isinstance(rows,list) or not rows or len(rows)>spec["max_native_records"]
            or type(projection.get("record_count")) is not int or projection["record_count"] != len(rows)
            or not isinstance(projection.get("engine"),dict) or not projection["engine"]
            or not isinstance(projection.get("limitations"),list)
            or any(not isinstance(r,dict) or not isinstance(r.get("text"),str)
                   or not isinstance(r.get("locator"),dict) or not r["locator"] for r in rows)
            or len(legacy.encoded(projection)) > spec["max_projection_chars"]):
        error("PROJECTION_INVALID", "profile/shape/source binding")
    if any(r.get("id") != f"record-{i:06d}" for i,r in enumerate(rows,1)):
        error("PROJECTION_INVALID", "record identity/ordering")
    if projection["format"] in {"docx","xlsx"}:
        coverage = projection.get("coverage")
        if not isinstance(coverage,dict) or not isinstance(coverage.get("parts"),list):
            error("PROJECTION_INVALID", "native package coverage")
        parts = {p.get("part"):p.get("sha256") for p in coverage["parts"] if isinstance(p,dict)}
        if any(not isinstance(r.get("native"),dict) or r["locator"].get("part") not in parts
               or not isinstance(r["locator"].get("part_sha256"),str)
               or re.fullmatch(r"[0-9a-f]{64}",r["locator"]["part_sha256"]) is None
               or r["locator"]["part_sha256"] != parts[r["locator"]["part"]] for r in rows):
            error("PROJECTION_INVALID", "native record/part lineage")
        engine = projection["engine"]
        if (engine.get("profile") != PROFILE or any(not isinstance(engine.get(k),str)
                or re.fullmatch(r"[0-9a-f]{64}",engine[k]) is None for k in ("module_sha256","projector_sha256"))):
            error("PROJECTION_INVALID", "native extractor identity")


def projection_text(projection: dict) -> str:
    return "\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True) for r in projection["records"]) + "\n"
