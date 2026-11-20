"""Bounded, offline text evidence for native documents and workbooks.

This module is also copied as a standalone helper into legacy rule containers.
It does not render images, execute macros, follow links, or recalculate formulas.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import io
from importlib import metadata
import json
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile


NATIVE_TEXT_VERSION = "wildclawbench.native-artifact-text/v1"
NATIVE_TEXT_EXTENSIONS = frozenset({".docx", ".xlsx", ".pdf"})
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_XML_BYTES = 16 * 1024 * 1024
MAX_ZIP_MEMBERS = 5000
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


class NativeTextError(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


def is_native_text_format(path: str | Path) -> bool:
    return Path(path).suffix.lower() in NATIVE_TEXT_EXTENSIONS


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    try:
        info = archive.getinfo(name)
    except KeyError as exc:
        raise NativeTextError("NATIVE_TEXT_INVALID", f"missing OOXML part: {name}") from exc
    if info.file_size > MAX_XML_BYTES:
        raise NativeTextError("NATIVE_TEXT_LIMIT", f"OOXML part exceeds extraction limit: {name}")
    raw = archive.read(info)
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise NativeTextError("NATIVE_TEXT_INVALID", "XML entity declarations are unsupported")
    try:
        return ET.fromstring(raw)
    except ET.ParseError as exc:
        raise NativeTextError("NATIVE_TEXT_INVALID", f"invalid OOXML part: {name}") from exc


def _archive(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise NativeTextError("NATIVE_TEXT_INVALID", "native Office file is not a valid ZIP") from exc
    members = archive.infolist()
    if (len(members) > MAX_ZIP_MEMBERS or sum(info.file_size for info in members) > MAX_ZIP_BYTES
            or len({info.filename for info in members}) != len(members)):
        archive.close()
        raise NativeTextError("NATIVE_TEXT_LIMIT", "Office package exceeds extraction limits or has duplicate members")
    for info in members:
        parts = info.filename.rstrip("/").split("/")
        if info.flag_bits & 1 or "\\" in info.filename or info.filename.startswith("/") or any(part in {"", ".", ".."} for part in parts):
            archive.close()
            raise NativeTextError("NATIVE_TEXT_INVALID", "encrypted or unsafe Office package member")
    return archive


def _word_text(node: ET.Element) -> str:
    out = []
    for part in node.iter():
        if part.tag == W + "t":
            out.append(part.text or "")
        elif part.tag == W + "tab":
            out.append("\t")
        elif part.tag in {W + "br", W + "cr"}:
            out.append("\n")
    return "".join(out)


def _docx(data: bytes) -> tuple[list[dict], list[str]]:
    records = []
    with _archive(data) as archive:
        root = _xml(archive, "word/document.xml")
        body = root.find(W + "body")
        if body is None:
            raise NativeTextError("NATIVE_TEXT_INVALID", "Word document body is missing")
        paragraph_number = table_number = 0
        def body_nodes(parent):
            for node in parent:
                if node.tag in {W + "p", W + "tbl"}:
                    yield node
                elif node.tag in {W + "sdt", W + "sdtContent", W + "customXml"}:
                    yield from body_nodes(node)
        for node in body_nodes(body):
            if node.tag == W + "p":
                paragraph_number += 1
                text = _word_text(node)
                if text:
                    records.append({"locator": f"paragraph:{paragraph_number}", "text": text})
            elif node.tag == W + "tbl":
                table_number += 1
                for row_number, row in enumerate(node.findall(W + "tr"), 1):
                    for cell_number, cell in enumerate(row.findall(W + "tc"), 1):
                        text = "\n".join(_word_text(p) for p in cell.iter(W + "p"))
                        records.append({"locator": f"table:{table_number}/row:{row_number}/cell:{cell_number}", "text": text})
        for name in sorted(archive.namelist()):
            if re.fullmatch(r"word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml", name):
                for index, paragraph in enumerate(_xml(archive, name).iter(W + "p"), 1):
                    text = _word_text(paragraph)
                    if text:
                        records.append({"locator": f"{name}/paragraph:{index}", "text": text})
    if not any(record["text"].strip() for record in records):
        raise NativeTextError("NATIVE_TEXT_UNAVAILABLE", "Word file has no extractable text; visual evidence may be required")
    return records, ["Text and tables only; images, embedded objects and layout are not interpreted.",
                     "Inserted text is included; deleted text stored as delText is excluded."]


def _cell_date(value: str, code: str, epoch_1904: bool) -> str | None:
    if re.search(r"\[[hms]+\]", code, re.I):
        return None  # elapsed durations are not calendar dates
    plain = re.sub(r'"[^\"]*"|\\.|\[[^\]]*\]', "", code).lower()
    if not re.search(r"y{2,4}|d{1,4}|h{1,2}|s{1,2}", plain):
        return None
    try:
        serial = float(value)
        if epoch_1904:
            epoch = datetime(1904, 1, 1)
        else:
            if 60 <= serial < 61:
                return "1900-02-29 (Excel serial calendar)"
            epoch = datetime(1899, 12, 30) if serial >= 60 else datetime(1899, 12, 31)
        return (epoch + timedelta(days=serial)).isoformat(timespec="seconds")
    except (ValueError, OverflowError):
        return None


def _xlsx(data: bytes) -> tuple[list[dict], list[str]]:
    records = []
    with _archive(data) as archive:
        workbook = _xml(archive, "xl/workbook.xml")
        relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
        targets = {node.attrib.get("Id"): node.attrib.get("Target") for node in relationships
                   if node.attrib.get("TargetMode") != "External"}
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = ["".join((part.text or "") if part.tag == S + "t" else
                               "".join(child.text or "" for child in part.findall(S + "t")) if part.tag == S + "r" else ""
                               for part in node)
                       for node in _xml(archive, "xl/sharedStrings.xml").findall(S + "si")]
        formats = {0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00",
                   9: "0%", 10: "0.00%", 11: "0.00E+00", 12: "# ?/?", 13: "# ??/??",
                   14: "mm-dd-yy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy",
                   18: "h:mm AM/PM", 19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss", 22: "m/d/yy h:mm",
                   45: "mm:ss", 46: "[h]:mm:ss", 47: "mmss.0"}
        style_formats = []
        style_ids = []
        if "xl/styles.xml" in archive.namelist():
            styles = _xml(archive, "xl/styles.xml")
            for item in styles.findall(f"{S}numFmts/{S}numFmt"):
                formats[int(item.attrib["numFmtId"])] = item.attrib["formatCode"]
            style_ids = [int(item.attrib.get("numFmtId", "0")) for item in styles.findall(f"{S}cellXfs/{S}xf")]
            style_formats = [formats.get(identifier, "") for identifier in style_ids]
        properties = workbook.find(S + "workbookPr")
        epoch_1904 = properties is not None and properties.attrib.get("date1904") in {"1", "true"}
        sheets = workbook.find(S + "sheets")
        if sheets is None:
            raise NativeTextError("NATIVE_TEXT_INVALID", "workbook has no sheets")
        for sheet in sheets:
            target = targets.get(sheet.attrib.get(R + "id"))
            if not isinstance(target, str):
                raise NativeTextError("NATIVE_TEXT_INVALID", "worksheet relationship unavailable")
            part = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
            if not part.startswith("xl/") or ".." in part.split("/"):
                raise NativeTextError("NATIVE_TEXT_INVALID", "worksheet relationship escapes workbook")
            name = sheet.attrib.get("name", "")
            records.append({"locator": f"sheet:{name}", "state": sheet.attrib.get("state", "visible")})
            for cell in _xml(archive, part).iter(S + "c"):
                address = cell.attrib.get("r")
                if not address or not re.fullmatch(r"[A-Z]+[1-9][0-9]*", address):
                    raise NativeTextError("NATIVE_TEXT_INVALID", "worksheet cell address missing/invalid")
                value_node, formula = cell.find(S + "v"), cell.find(S + "f")
                kind = cell.attrib.get("t", "n")
                value = value_node.text if value_node is not None else None
                if kind == "str" and value_node is not None and value is None:
                    value = ""  # a stored empty-string result is not an absent cache
                if kind == "s" and value is not None:
                    try:
                        index = int(value)
                        if index < 0:
                            raise ValueError("negative shared string index")
                        value = strings[index]
                    except (ValueError, IndexError) as exc:
                        raise NativeTextError("NATIVE_TEXT_INVALID", "invalid shared string index") from exc
                elif kind == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(S + "t"))
                elif kind == "b" and value is not None:
                    value = value == "1"
                record = {"locator": f"{name}!{address}", "type": kind, "value": value}
                if formula is not None:
                    record["formula"] = formula.text or ""
                    record["formula_attributes"] = dict(formula.attrib)
                    record["cached_value_available"] = value is not None
                style = int(cell.attrib.get("s", "0"))
                if kind == "n" and isinstance(value, str) and 0 <= style < len(style_formats):
                    code = style_formats[style]
                    record.update(number_format_id=style_ids[style], number_format=code)
                    date = _cell_date(value, code, epoch_1904)
                    if date:
                        record["interpreted_date"] = date
                if value is not None or formula is not None:
                    records.append(record)
    return records, ["Cell contents and stored formula caches only; formulas are not recalculated.",
                     "Charts, images, macros, external links and layout are not interpreted.",
                     "Date serials are annotated using stored number formats and the workbook epoch."]


def _pdf(data: bytes) -> tuple[list[dict], list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise NativeTextError("NATIVE_TEXT_DEPENDENCY_MISSING", "PDF text extraction requires pypdf in the scoring runtime") from exc
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise NativeTextError("NATIVE_TEXT_UNAVAILABLE", "encrypted PDF is not text evidence")
        records = [{"locator": f"page:{number}", "text": page.extract_text() or ""}
                   for number, page in enumerate(reader.pages, 1)]
    except NativeTextError:
        raise
    except Exception as exc:
        raise NativeTextError("NATIVE_TEXT_INVALID", "PDF text extraction failed") from exc
    if not any(record["text"].strip() for record in records):
        raise NativeTextError("NATIVE_TEXT_UNAVAILABLE", "PDF has no extractable text; visual evidence is required")
    return records, ["Extracted PDF text only; images, scans, charts and layout are not interpreted."]


def extract_native_text(path: str | Path, *, max_chars: int = 200_000,
                        record_offset: int = 0, record_limit: int | None = None) -> dict:
    path = Path(path)
    if not is_native_text_format(path):
        raise NativeTextError("NATIVE_TEXT_UNSUPPORTED", "unsupported native text format")
    if path.is_symlink() or not path.is_file():
        raise NativeTextError("NATIVE_TEXT_INVALID", "native evidence must be a regular file")
    if (path.stat().st_size > MAX_FILE_BYTES or max_chars < 1 or type(record_offset) is not int or record_offset < 0
            or record_limit is not None and (type(record_limit) is not int or record_limit < 1)):
        raise NativeTextError("NATIVE_TEXT_LIMIT", "native text extraction size limit")
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise NativeTextError("NATIVE_TEXT_LIMIT", "native evidence grew beyond extraction limit")
    try:
        records, limitations = {".docx": _docx, ".xlsx": _xlsx, ".pdf": _pdf}[path.suffix.lower()](data)
    except (KeyError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, NativeTextError):
            raise
        raise NativeTextError("NATIVE_TEXT_INVALID", "malformed native document") from exc
    selected = records[record_offset:] if record_limit is None else records[record_offset:record_offset + record_limit]
    text = "\n".join(json.dumps(record, ensure_ascii=False, sort_keys=True) for record in selected)
    original_chars = len(text)
    text = text[:max_chars]
    engine = {"name": "stdlib-ooxml", "version": NATIVE_TEXT_VERSION}
    if path.suffix.lower() == ".pdf":
        try:
            engine = {"name": "pypdf", "version": metadata.version("pypdf")}
        except metadata.PackageNotFoundError:
            engine = {"name": "pypdf", "version": "unavailable"}
    return {"schema_version": NATIVE_TEXT_VERSION, "source_sha256": hashlib.sha256(data).hexdigest(),
            "format": path.suffix.lower()[1:], "text": text,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "original_chars": original_chars, "included_chars": len(text), "truncated": original_chars > len(text),
            "record_count": len(records), "record_offset": record_offset,
            "selected_record_count": len(selected), "engine": engine,
            "limitations": [*limitations, "Text extraction is not a native-application or visual usability check."]}
