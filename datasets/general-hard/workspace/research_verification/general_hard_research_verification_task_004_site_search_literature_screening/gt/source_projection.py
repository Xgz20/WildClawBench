"""Offline projections of independently acquired source bodies.

This is an authoring helper awaiting integration, not a source fetcher, semantic
judge, candidate-cache authenticator, or completed attempt runtime. The caller
must establish that body_bytes and any existing PDF projection came from its
independent evidence bundle. No URL/domain policy or event facts live here.
"""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any

SCHEMA_VERSION = "h030.offline-source-projection/v1"
PDF_PROJECTION_SCHEMA = "wildclawbench.research-source-text/v1"
MAX_BODY_BYTES = 20 * 1024 * 1024
_ASSIGN = re.compile(r"window\s*\.\s*_ROUTER_DATA\s*=(?!=|>)")
_PLACEHOLDER = re.compile(
    r"enable javascript|javascript (?:is )?(?:required|disabled)|"
    r"you need to enable javascript|loading\s*[.\u2026]*$|"
    r"请(?:开启|启用).*javascript|加载中|正在加载", re.I
)


class DuplicateJSONKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DuplicateJSONKey(f"Duplicate JSON object key: {key!r}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")


_DECODER = json.JSONDecoder(
    object_pairs_hook=_unique_object, parse_constant=_reject_constant
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _clean(text: str) -> str:
    return "\n".join(
        line for line in (re.sub(r"[ \t\f\v]+", " ", x).strip()
                          for x in text.splitlines()) if line
    )


def _pointer(parts: list[Any]) -> str:
    return "/" + "/".join(
        str(x).replace("~", "~0").replace("/", "~1") for x in parts
    )


class _HTML(HTMLParser):
    """Static text and script payload collection; never executes script."""
    _BLOCK = {"p", "div", "article", "main", "section", "h1", "h2", "h3",
              "h4", "li", "tr", "br", "time", "td"}
    _SKIP = {"script", "style", "noscript", "template", "nav", "footer", "head"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.frames: list[tuple[str, bool]] = []
        self.scripts: list[dict[str, Any]] = []
        self.active_script: dict[str, Any] | None = None
        self.parts: list[str] = []
        self.semantic_parts: list[str] = []
        self.semantic_depth = 0
        self.paragraphs: list[list[str]] = []
        self.current_p: list[str] | None = None
        self.meta: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script":
            self.active_script = {
                "index": len(self.scripts), "attrs": values, "parts": []
            }
        if tag == "meta":
            self.meta.append(values)
        if tag in self._BLOCK:
            self.parts.append("\n")
            self.semantic_parts.append("\n")
        inherited = self.frames[-1][1] if self.frames else False
        hidden = (inherited or tag in self._SKIP or "hidden" in values
                  or values.get("aria-hidden", "").lower() == "true")
        if tag not in {"meta", "link", "br", "hr", "img", "input", "source",
                       "area", "base", "embed", "param", "track", "wbr"}:
            self.frames.append((tag, hidden))
        if tag in {"article", "main"} and not hidden:
            self.semantic_depth += 1
        if tag == "p" and not hidden:
            self.current_p = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in {"meta", "link", "br", "hr", "img", "input", "source",
                       "area", "base", "embed", "param", "track", "wbr"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.active_script is not None:
            self.active_script["text"] = "".join(self.active_script.pop("parts"))
            self.scripts.append(self.active_script)
            self.active_script = None
        if tag == "p" and self.current_p is not None:
            self.paragraphs.append(self.current_p)
            self.current_p = None
        # Tolerate ordinary mismatched closing tags without retaining hidden
        # state forever. This is text projection, not browser DOM emulation.
        for index in range(len(self.frames) - 1, -1, -1):
            if self.frames[index][0] == tag:
                removed = self.frames[index:]
                self.semantic_depth = max(
                    0, self.semantic_depth - sum(
                        t in {"article", "main"} and not hidden
                        for t, hidden in removed
                    )
                )
                del self.frames[index:]
                break
        if tag in self._BLOCK:
            self.parts.append("\n")
            self.semantic_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.active_script is not None:
            self.active_script["parts"].append(data)
        hidden = self.frames[-1][1] if self.frames else False
        if not hidden:
            self.parts.append(data)
            if self.semantic_depth:
                self.semantic_parts.append(data)
            if self.current_p is not None:
                self.current_p.append(data)


def _skip_quoted(script: str, index: int) -> int:
    quote = script[index]
    index += 1
    while index < len(script):
        if script[index] == "\\":
            index += 2
        elif script[index] == quote:
            return index + 1
        else:
            index += 1
    return len(script)


def _router_assignments(script: str) -> list[dict[str, Any]]:
    """Recognize top-level literal assignments without interpreting JavaScript.

    Quoted strings, templates, comments, and other statements are skipped. Only
    an explicit dot-notation assignment at a top-level statement boundary is
    accepted. JSONDecoder parses its value; expression syntax is rejected.
    """
    found: list[dict[str, Any]] = []
    index, depth, boundary = 0, 0, True
    while index < len(script):
        if script[index].isspace():
            index += 1
            continue
        if script.startswith("//", index):
            end = script.find("\n", index + 2)
            index = len(script) if end < 0 else end + 1
            continue
        if script.startswith("/*", index):
            end = script.find("*/", index + 2)
            index = len(script) if end < 0 else end + 2
            continue
        if script[index] == "/":
            # Treat unknown slash expressions conservatively as a possible JS
            # regex literal. This can omit an unrelated division expression,
            # but cannot discover a fake assignment inside a regex string.
            index += 1
            in_class = False
            while index < len(script):
                char = script[index]
                if char == "\\":
                    index += 2
                    continue
                if char == "[":
                    in_class = True
                elif char == "]":
                    in_class = False
                elif char == "/" and not in_class:
                    index += 1
                    break
                index += 1
            boundary = False
            continue
        match = _ASSIGN.match(script, index) if boundary and depth == 0 else None
        if match:
            value_start = match.end()
            while value_start < len(script) and script[value_start].isspace():
                value_start += 1
            item: dict[str, Any] = {"assignment_offset": index,
                                    "json_offset": value_start}
            try:
                value, end = _DECODER.raw_decode(script, value_start)
                trailing = end
                while trailing < len(script) and script[trailing].isspace():
                    trailing += 1
                if trailing < len(script) and script[trailing] != ";":
                    raise ValueError("JSON literal followed by unsupported expression")
                if not isinstance(value, dict):
                    raise ValueError("Router state must be a JSON object")
                item.update(value=value, json_end_offset=end,
                            json_literal_sha256=_sha(
                                script[value_start:end].encode("utf-8")))
                index, boundary = trailing, False
            except (ValueError, RecursionError) as exc:
                item.update(error_type=type(exc).__name__, error=str(exc))
                # Never recover a body by guessing where malformed JSON ends.
                index = len(script)
            found.append(item)
            continue
        char = script[index]
        if char in "'\"\x60":
            index = _skip_quoted(script, index)
            boundary = False
            continue
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth = max(0, depth - 1)
        elif char == ";" and depth == 0:
            boundary = True
            index += 1
            continue
        boundary = False
        index += 1
    return found


def _error(result: dict[str, Any], code: str, detail: str, **location: Any) -> None:
    result["errors"].append({"type": code, "detail": detail, **location})


def _observed(metadata: dict[str, Any], kind: str, value: Any, **locator: Any) -> None:
    metadata["observations"].append({
        "observed_type": kind, "value": copy.deepcopy(value),
        "value_type": type(value).__name__, **locator,
    })


def _jsonld_metadata(parser: _HTML, result: dict[str, Any]) -> None:
    metadata = result["metadata"]
    for script in parser.scripts:
        if script["attrs"].get("type", "").lower().split(";")[0].strip() != "application/ld+json":
            continue
        try:
            value, end = _DECODER.raw_decode(script["text"].lstrip())
            if script["text"].lstrip()[end:].strip():
                raise ValueError("Trailing data after JSON-LD")
        except (ValueError, RecursionError) as exc:
            metadata["complete"] = False
            result["warnings"].append({
                "type": "invalid_jsonld", "script_index": script["index"],
                "detail": str(exc),
            })
            continue

        def walk(node: Any, path: list[Any]) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    child_path = path + [key]
                    if key in {"datePublished", "dateModified"}:
                        _observed(
                            metadata, "jsonld_field", child, property=key,
                            script_index=script["index"],
                            json_path=child_path, json_pointer=_pointer(child_path),
                        )
                    walk(child, child_path)
            elif isinstance(node, list):
                for i, child in enumerate(node):
                    walk(child, path + [i])
        try:
            walk(value, [])
        except RecursionError:
            metadata["complete"] = False
            result["warnings"].append({"type": "jsonld_depth_exceeded",
                                       "script_index": script["index"]})
    for index, item in enumerate(parser.meta):
        prop = item.get("property") or item.get("name")
        if prop in {"article:published_time", "article:modified_time",
                    "published_time", "datePublished", "dateModified"} and "content" in item:
            _observed(metadata, "html_meta", item["content"], property=prop,
                      meta_index=index)


def _project_html(body: bytes, media_type: str, result: dict[str, Any]) -> None:
    charset_match = re.search(r"charset\s*=\s*[\"']?([^;\s\"']+)", media_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8-sig"
    try:
        text = body.decode(charset, errors="strict")
        parser = _HTML()
        parser.feed(text)
        parser.close()
    except (UnicodeError, LookupError, RecursionError, ValueError) as exc:
        _error(result, "html_parse_or_decode_error", str(exc))
        return
    result["provenance"]["decoded_charset"] = charset
    _jsonld_metadata(parser, result)
    candidates: list[dict[str, Any]] = []
    assignment_count = 0
    for script in parser.scripts:
        # JSON data script values cannot be JavaScript assignment statements.
        if script["attrs"].get("type", "").lower().startswith("application/ld+json"):
            continue
        for assignment in _router_assignments(script["text"]):
            assignment_count += 1
            location = {"script_index": script["index"],
                        "assignment_offset": assignment["assignment_offset"]}
            if "error" in assignment:
                _error(result, "invalid_router_json", assignment["error"],
                       parser_error_type=assignment["error_type"], **location)
                continue
            state = assignment["value"]
            loader = state.get("loaderData")
            if not isinstance(loader, dict):
                _error(result, "unsupported_router_structure",
                       "loaderData is absent or is not an object", **location)
                continue
            local_count = 0
            for page_key, page in loader.items():
                if not isinstance(page, dict) or "curDoc" not in page:
                    continue
                doc = page["curDoc"]
                if not isinstance(doc, dict) or "MDContent" not in doc:
                    continue
                local_count += 1
                path = ["loaderData", page_key, "curDoc", "MDContent"]
                if not isinstance(doc["MDContent"], str) or not doc["MDContent"].strip():
                    _error(result, "invalid_mdcontent",
                           "MDContent must be a nonempty string",
                           json_path=path, **location)
                    continue
                original = doc["MDContent"]
                try:
                    original_bytes = original.encode("utf-8", errors="strict")
                except UnicodeError as exc:
                    _error(result, "invalid_mdcontent_unicode", str(exc),
                           json_path=path, **location)
                    continue
                projected = re.sub(r"<br\s*/?>", "\n",
                                   original.replace("\r\n", "\n").replace("\r", "\n"),
                                   flags=re.I)
                record = {
                    "locator": {"kind": "router_json", "script_index": script["index"],
                                "assignment_offset": assignment["assignment_offset"],
                                "json_path": path, "json_pointer": _pointer(path)},
                    "text": projected, "raw_mdcontent": original,
                    "raw_mdcontent_sha256": _sha(original_bytes),
                    "text_sha256": _sha(projected.encode("utf-8")),
                    "json_literal_sha256": assignment["json_literal_sha256"],
                }
                for field in ("Title", "PDFURL"):
                    if field in doc:
                        field_path = ["loaderData", page_key, "curDoc", field]
                        _observed(result["metadata"], "router_json_field", doc[field],
                                  property=field, script_index=script["index"],
                                  json_path=field_path, json_pointer=_pointer(field_path))
                record["_signature"] = _sha(_canonical({
                    "MDContent": original,
                    "Title": {"present": "Title" in doc, "value": doc.get("Title")},
                    "PDFURL": {"present": "PDFURL" in doc, "value": doc.get("PDFURL")},
                }))
                candidates.append(record)
            if local_count == 0:
                _error(result, "router_document_missing",
                       "No loaderData page has curDoc.MDContent", **location)
    result["provenance"]["router_assignment_count"] = assignment_count
    result["provenance"]["router_candidate_count"] = len(candidates)
    if assignment_count:
        signatures = {item.pop("_signature") for item in candidates}
        result["records"] = candidates
        if len(signatures) > 1:
            _error(result, "ambiguous_router_documents",
                   "Conflicting MDContent/Title/PDFURL candidates; none selected")
        result["complete"] = bool(candidates) and not result["errors"]
        result["provenance"]["projection_method"] = "literal-router-json-mdcontent"
        return
    visible = _clean("".join(parser.parts))
    semantic = _clean("".join(parser.semantic_parts))
    paragraphs = [_clean("".join(x)) for x in parser.paragraphs]
    substantive = semantic if len(re.sub(r"\s", "", semantic)) >= 32 else "\n".join(
        p for p in paragraphs if len(re.sub(r"\s", "", p)) >= 32
    )
    if not substantive or _PLACEHOLDER.search(substantive):
        _error(result, "unresolved_dynamic_or_insufficient_static_body",
               "No substantive static article/main/paragraph text; refusing a shell")
        result["provenance"]["static_visible_text_sha256"] = _sha(visible.encode("utf-8"))
        return
    result["records"] = [{
        "locator": {"kind": "static_html", "record": 1},
        "text": substantive, "text_sha256": _sha(substantive.encode("utf-8")),
    }]
    result["complete"] = True
    result["provenance"]["projection_method"] = "stdlib-static-html-semantic-text"


def _project_pdf(existing: Any, result: dict[str, Any]) -> None:
    if not isinstance(existing, dict):
        _error(result, "independent_pdf_projection_required",
               "PDF projection must come from the caller's independent bundle")
        return
    if existing.get("schema_version") != PDF_PROJECTION_SCHEMA:
        _error(result, "unsupported_pdf_projection_schema",
               "Expected an independent research-source-text/v1 projection")
        return
    try:
        existing_digest = _sha(_canonical(existing))
    except (TypeError, ValueError, RecursionError) as exc:
        _error(result, "invalid_pdf_projection_serialization", str(exc))
        return
    if existing.get("source_sha256") != result["provenance"]["body_sha256"]:
        _error(result, "pdf_body_sha_mismatch", "Existing page projection is not bound to these bytes")
        return
    if existing.get("complete") is not True:
        _error(result, "pdf_projection_incomplete", "Existing page projection is incomplete")
        return
    records = existing.get("records")
    if not isinstance(records, list) or not records:
        _error(result, "invalid_pdf_records", "Expected a nonempty page-record list")
        return
    pages: list[int] = []
    projected: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, dict):
            _error(result, "invalid_pdf_record", "Page record must be an object")
            return
        page = item.get("locator", {}).get("page") if isinstance(item.get("locator"), dict) else None
        value = item.get("text")
        if type(page) is not int or page < 1 or not isinstance(value, str):
            _error(result, "invalid_pdf_record", "Each page needs positive integer locator.page and string text")
            return
        try:
            digest = _sha(value.encode("utf-8", errors="strict"))
        except UnicodeError as exc:
            _error(result, "invalid_pdf_text_unicode", str(exc), page=page)
            return
        if "text_sha256" in item and item["text_sha256"] != digest:
            _error(result, "pdf_text_sha_mismatch", "Supplied page text hash is incorrect", page=page)
            return
        pages.append(page)
        projected.append({"locator": {"kind": "pdf_page", "page": page},
                          "text": value, "text_sha256": digest})
    if pages != list(range(1, len(pages) + 1)):
        _error(result, "invalid_pdf_page_sequence", "Page records must be unique and contiguous from page1")
        return
    if not any(item["text"].strip() for item in projected):
        _error(result, "empty_pdf_text", "Page projection contains no extracted text")
        return
    raw_metadata = existing.get("raw_metadata") or {}
    if not isinstance(raw_metadata, dict):
        _error(result, "invalid_pdf_metadata", "raw_metadata must be an object")
        return
    result["records"] = projected
    for key, value in raw_metadata.items():
        _observed(result["metadata"], "pdf_raw_metadata", value, property=key)
    result["provenance"].update(
        projection_method="independent-bundle-pdf-pages",
        existing_projection_canonical_sha256=existing_digest,
        existing_projection_engine=copy.deepcopy(existing.get("engine")),
    )
    result["complete"] = True


def project_source(body_bytes: bytes, media_type: str,
                   existing_projection: dict[str, Any] | None = None) -> dict[str, Any]:
    """Project an independent fetched body, without network or script execution.

    complete describes structural body projection, never semantic truth or
    historical availability. metadata records only actual observed values.
    PDF trust provenance must be established by the caller; a matching hash
    alone cannot authenticate an arbitrarily supplied candidate projection.
    """
    if not isinstance(body_bytes, bytes):
        raise TypeError("body_bytes must be bytes")
    if not isinstance(media_type, str):
        raise TypeError("media_type must be a string")
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "complete": False, "records": [],
        "metadata": {"complete": True, "observations": [],
                     "policy": "Observed source fields only; no inferred publication dates"},
        "errors": [], "warnings": [],
        "provenance": {
            "body_sha256": _sha(body_bytes), "body_bytes": len(body_bytes),
            "media_type_observed": media_type,
            "trust_boundary": "Caller must supply independently acquired source body and PDF projection",
            "network_used": False, "javascript_executed": False,
        },
    }
    if len(body_bytes) > MAX_BODY_BYTES:
        _error(result, "body_size_limit", "Body exceeds deterministic projection size limit")
    elif media_type.split(";", 1)[0].strip().lower() in {"text/html", "application/xhtml+xml"}:
        _project_html(body_bytes, media_type, result)
    elif media_type.split(";", 1)[0].strip().lower() == "application/pdf":
        _project_pdf(existing_projection, result)
    else:
        _error(result, "unsupported_media_type", "Only HTML and independently projected PDF are supported")
    result["provenance"]["records_canonical_sha256"] = _sha(_canonical(result["records"]))
    result["provenance"]["metadata_canonical_sha256"] = _sha(_canonical(result["metadata"]))
    return result


def write_derived_projection(projection: dict[str, Any],
                             rule_evidence_dir: str | Path,
                             stem: str = "source") -> dict[str, Any]:
    """Create managed derived files; never overwrite a body, bundle, or GT.

    The caller chooses RULE_EVIDENCE_DIR and must keep it separate from inputs.
    Incomplete projections get a diagnostic JSON only, with no body text file.
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", stem):
        raise ValueError("stem must be a plain safe filename component")
    if projection.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unexpected projection schema")
    body_sha = projection.get("provenance", {}).get("body_sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", body_sha):
        raise ValueError("Missing source body SHA256")
    root = Path(rule_evidence_dir)
    if root.is_symlink():
        raise ValueError("Evidence directory cannot be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    prefix = root / f"{stem}-{body_sha[:16]}"
    json_path = prefix.with_name(prefix.name + ".projection.json")
    text_path = prefix.with_name(prefix.name + ".text.txt")
    outputs = [(json_path, json.dumps(projection, ensure_ascii=True, indent=2).encode("utf-8") + b"\n")]
    if projection["complete"] is True:
        text = "\n\n".join(
            f"[record {i + 1}]\n{record['text']}" for i, record in enumerate(projection["records"])
        )
        outputs.append((text_path, text.encode("utf-8")))
    if any(path.exists() or path.is_symlink() for path, _ in outputs):
        raise FileExistsError("Derived evidence output already exists; refusing overwrite")
    result = []
    for path, payload in outputs:
        with path.open("xb") as handle:
            handle.write(payload)
        result.append({"path": str(path), "sha256": _sha(payload), "bytes": len(payload)})
    return {"complete": projection["complete"], "outputs": result}


# H030 format extension: actual XML nodes and plain text, never a fact oracle.
import io
import xml.etree.ElementTree as ET

_BASE_PROJECT_SOURCE = project_source


def _xml_local(tag):
    return tag.rsplit('}', 1)[-1] if isinstance(tag, str) else ''


def _xml_projection(body, media):
    result = {'schema_version': SCHEMA_VERSION, 'complete': False, 'records': [],
              'metadata': {'complete': True, 'observations': [], 'policy': 'Actual XML nodes only; publication roles require Judge'},
              'xml_nodes': [], 'errors': [], 'warnings': [],
              'provenance': {'body_sha256': _sha(body), 'body_bytes': len(body), 'media_type_observed': media,
                             'network_used': False, 'javascript_executed': False, 'projection_method': 'offline-ElementTree-node-spans/v1'}}
    try:
        if len(body) > MAX_BODY_BYTES:
            raise ValueError('XML body exceeds deterministic size limit')
        # Expat/ElementTree does not retrieve an external DTD. Arbitrary entity
        # declarations are refused before parsing; an ordinary DOCTYPE is legal.
        if re.search(br'<!\s*ENTITY\b', body.replace(b'\x00', b''), re.I):
            raise ValueError('arbitrary XML entity declarations unsupported by safe extractor')
        namespaces = []
        for _, pair in ET.iterparse(io.BytesIO(body), events=('start-ns',)):
            if pair not in namespaces:
                namespaces.append(pair)
        root = ET.fromstring(body)
        buffer = []
        length = 0
        nodes = []
        def add(value):
            nonlocal length
            if value:
                buffer.append(value); length += len(value)
        def visit(element, path, namespace_path):
            if len(nodes) >= 100000:
                raise ValueError('XML node count exceeds deterministic limit')
            start = length
            item = {'path': path, 'namespace_path': namespace_path, 'tag': element.tag,
                    'local_name': _xml_local(element.tag), 'attributes': dict(element.attrib),
                    'text_start': start}
            nodes.append(item)
            add(element.text)
            counts = {}
            for child in element:
                counts[child.tag] = counts.get(child.tag, 0) + 1
                index = counts[child.tag]
                visit(child, path + '/' + _xml_local(child.tag) + f'[{index}]', namespace_path + '/' + child.tag + f'[{index}]')
                add(child.tail)
            item['text_end'] = length
            # Date parts are composed only from this one real parent node.
            parts = {}
            for child in element:
                local = _xml_local(child.tag).lower()
                if local in {'year', 'month', 'day'}:
                    if local in parts:
                        parts = {}; break
                    parts[local] = ''.join(child.itertext()).strip()
            if parts.get('year'):
                result['metadata']['observations'].append({'observed_type': 'xml_date_parts',
                    'property': item['local_name'], 'parts': parts, 'value': dict(parts),
                    'path': path, 'namespace_path': namespace_path, 'attributes': dict(element.attrib),
                    'date_role_observed': {'tag': element.tag, 'attributes': dict(element.attrib)},
                    'text_start': start, 'text_end': length})
            if len(element) == 0 and (element.text or '').strip():
                result['metadata']['observations'].append({'observed_type': 'xml_leaf',
                    'property': item['local_name'], 'value': element.text.strip(), 'path': path,
                    'namespace_path': namespace_path, 'attributes': dict(element.attrib)})
        visit(root, '/' + _xml_local(root.tag) + '[1]', '/' + root.tag + '[1]')
        text = ''.join(buffer)
        if not text.strip():
            raise ValueError('XML has no extractable text')
        result['xml_nodes'] = nodes
        result['records'] = [{'locator': {'kind': 'xml_document', 'path': nodes[0]['path']},
                              'text': text, 'text_sha256': _sha(text.encode('utf-8'))}]
        result['provenance']['namespaces'] = namespaces
        result['provenance']['xml_node_table_sha256'] = _sha(_canonical(nodes))
        result['complete'] = True
    except (ET.ParseError, ValueError, UnicodeError, RecursionError) as exc:
        _error(result, 'safe_xml_projection_unresolved', str(exc))
    result['provenance']['records_canonical_sha256'] = _sha(_canonical(result['records']))
    result['provenance']['metadata_canonical_sha256'] = _sha(_canonical(result['metadata']))
    return result


def project_source(body_bytes, media_type, existing_projection=None):
    mime = media_type.split(';', 1)[0].strip().lower()
    sniff = body_bytes.lstrip().lower()
    xml = mime in {'application/xml', 'text/xml', 'application/jats+xml'} or mime.endswith('+xml') and mime != 'application/xhtml+xml' or sniff.startswith(b'<?xml')
    if xml:
        return _xml_projection(body_bytes, media_type)
    if mime in {'text/html', 'application/xhtml+xml', 'application/pdf'} or body_bytes.startswith(b'%PDF-') or sniff.startswith((b'<!doctype html', b'<html')):
        effective = 'application/pdf' if body_bytes.startswith(b'%PDF-') else 'text/html' if sniff.startswith((b'<!doctype html', b'<html')) else media_type
        return _BASE_PROJECT_SOURCE(body_bytes, effective, existing_projection)
    if mime.startswith('text/') or mime in {'application/json', 'application/octet-stream'}:
        if len(body_bytes) > MAX_BODY_BYTES:
            raise ValueError('Source body exceeds deterministic projection limit')
        try:
            encoding = re.search(r'charset\s*=\s*["\']?([\w-]+)', media_type, re.I)
            text = body_bytes.decode(encoding[1] if encoding else 'utf-8-sig', errors='strict')
        except (UnicodeError, LookupError) as exc:
            return {'schema_version': SCHEMA_VERSION, 'complete': False, 'records': [],
                    'metadata': {'complete': False, 'observations': []}, 'errors': [{'code': 'plain_decode_unresolved', 'message': str(exc)}],
                    'provenance': {'body_sha256': _sha(body_bytes), 'network_used': False}}
        return {'schema_version': SCHEMA_VERSION, 'complete': bool(text.strip()),
                'records': [{'locator': {'kind': 'plain_text', 'record': 1}, 'text': text, 'text_sha256': _sha(text.encode('utf-8'))}],
                'metadata': {'complete': True, 'observations': [], 'policy': 'Literal text, no inferred metadata'}, 'errors': [], 'warnings': [],
                'provenance': {'body_sha256': _sha(body_bytes), 'body_bytes': len(body_bytes), 'media_type_observed': media_type,
                               'projection_method': 'offline-literal-text/v1', 'network_used': False, 'javascript_executed': False,
                               'records_canonical_sha256': _sha(_canonical(text))}}
    return _BASE_PROJECT_SOURCE(body_bytes, media_type, existing_projection)
