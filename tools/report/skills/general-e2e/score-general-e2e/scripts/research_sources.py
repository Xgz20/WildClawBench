"""Independent public-source collection outside candidate and GT trees.

The collector is trusted scoring infrastructure. Hashes prove the frozen receipt
chain, not internet provenance on their own. It never supplies business scores,
historical publication dates, or semantic support labels.
"""

from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime, timezone
from html import unescape
from html.parser import HTMLParser
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo


POLICY_SCHEMA = "wildclawbench.research-source-policy/v1"
BUNDLE_SCHEMA = "wildclawbench.research-source-bundle/v1"
LOCK_SCHEMA = "wildclawbench.research-source-lock/v1"
PROJECTION_SCHEMA = "wildclawbench.research-source-text/v1"
BUNDLE_PATH = "private/research-sources"
LOCK_PATH = "research-sources.lock.json"
POLICY_PATH = "research_source_policy.json"
REUSE_SCHEMA = "wildclawbench.research-source-reuse-receipt/v1"
_REUSE_DEPTH: ContextVar[int] = ContextVar("research_source_reuse_depth", default=0)
POLICY_DEFAULTS = {
    "sources_key": "sources", "source_id_key": "source_id", "url_key": "url",
    "access_status_key": "access_status", "collect_statuses": ["read_full", "read_excerpt"],
    "citations_key": "citations", "citation_id_key": "citation_id",
    "quote_key": "quote", "locator_key": "locator", "max_sources": 40,
    "max_bytes_per_source": 20 * 1024 * 1024, "timeout_seconds": 60,
}


class ResearchSourceError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code, self.detail = code, detail
        super().__init__(f"{code}: {detail}" if detail else code)


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def write(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write(encoded(value))


def read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ResearchSourceError("RESEARCH_SOURCE_DOCUMENT_INVALID", str(path)) from exc
    if not isinstance(value, dict):
        raise ResearchSourceError("RESEARCH_SOURCE_DOCUMENT_INVALID", str(path))
    return value


def within(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\0" in relative:
        raise ResearchSourceError("RESEARCH_SOURCE_PATH_INVALID", str(relative))
    parts = PurePosixPath(relative).parts
    if PurePosixPath(relative).is_absolute() or any(part in {".", ".."} for part in parts):
        raise ResearchSourceError("RESEARCH_SOURCE_PATH_INVALID", relative)
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ResearchSourceError("RESEARCH_SOURCE_PATH_INVALID", relative)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise ResearchSourceError("RESEARCH_SOURCE_PATH_INVALID", relative) from exc
    return path


def inventory(root: Path) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ResearchSourceError("RESEARCH_SOURCE_PATH_INVALID", str(path))
        if path.is_file():
            rows.append({"path": path.relative_to(root).as_posix(), "size": path.stat().st_size,
                         "sha256": sha(path)})
    return rows


def policy(root: Path, manifest: dict) -> dict | None:
    contract = read(within(root, manifest["paths"]["contract"]))
    requirements = contract.get("scoring_runtime") or {}
    if not isinstance(requirements, dict):
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "scoring_runtime")
    if not requirements.get("research_sources"):
        return None
    if requirements["research_sources"] is not True:
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "research_sources must be boolean")
    path = within(within(root, manifest["paths"]["gt"]), POLICY_PATH)
    raw = read(path)
    required = {"schema_version", "ledger_path", "deliverable_paths", "as_of_inclusive", "timezone"}
    if set(raw) - required - set(POLICY_DEFAULTS) or not required <= set(raw) or raw.get("schema_version") != POLICY_SCHEMA:
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "unknown/missing policy fields")
    result = {**POLICY_DEFAULTS, **raw}
    for key in ("sources_key", "source_id_key", "url_key", "access_status_key", "citations_key",
                "citation_id_key", "quote_key", "locator_key"):
        if not isinstance(result[key], str) or not result[key]:
            raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", key)
    paths = result["deliverable_paths"]
    if (not isinstance(paths, list) or not paths or any(not isinstance(p, str) for p in paths)
            or len(paths) != len(set(paths)) or result["ledger_path"] not in paths):
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "deliverable_paths")
    for relative in paths:
        within(root, relative)
        if "gt" in PurePosixPath(relative).parts:
            raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "candidate paths cannot name gt")
    statuses = result["collect_statuses"]
    if not isinstance(statuses, list) or not statuses or any(not isinstance(s, str) or not s for s in statuses):
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "collect_statuses")
    for key, maximum in (("max_sources", 1000), ("max_bytes_per_source", 64 * 1024 * 1024), ("timeout_seconds", 300)):
        if type(result[key]) is not int or not 1 <= result[key] <= maximum:
            raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", key)
    try:
        date.fromisoformat(result["as_of_inclusive"])
        ZoneInfo(result["timezone"])
    except (ValueError, TypeError, KeyError) as exc:
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "fixed time scope") from exc
    return result


def _candidate_inputs(root: Path, manifest: dict, specification: dict) -> tuple[list[dict], dict, list[dict]]:
    candidate = within(root, manifest["paths"]["candidate_original"])
    if manifest.get("runtime", {}).get("path_resolution", {}).get("mode") == "mapped-nested":
        candidate = within(candidate, "workspace")
    bindings = []
    for relative in specification["deliverable_paths"]:
        path = within(candidate, relative)
        bindings.append({"path": relative, "exists": path.is_file(),
                         "sha256": sha(path) if path.is_file() else None})
    ledger = within(candidate, specification["ledger_path"])
    if not ledger.is_file():
        return bindings, {"status": "missing_ledger", "errors": ["ledger_missing"]}, []
    try:
        document = json.loads(ledger.read_text(encoding="utf-8"))
        sources = document[specification["sources_key"]]
        if not isinstance(sources, list):
            raise ValueError("sources must be an array")
    except (UnicodeError, ValueError, KeyError, TypeError):
        return bindings, {"status": "invalid_ledger", "errors": ["ledger_json_or_sources_invalid"]}, []
    selected, seen, citation_ids = [], set(), set()
    for index, row in enumerate(sources):
        if not isinstance(row, dict):
            return bindings, {"status": "invalid_ledger", "errors": [f"source {index} is not an object"]}, []
        source_id = row.get(specification["source_id_key"])
        citations = row.get(specification["citations_key"], [])
        if (not isinstance(source_id, str) or not source_id or source_id in seen
                or not isinstance(citations, list)):
            return bindings, {"status": "invalid_ledger", "errors": [f"source {index} ID/citations invalid"]}, []
        seen.add(source_id)
        for citation in citations:
            if not isinstance(citation, dict):
                return bindings, {"status": "invalid_ledger", "errors": [f"source {index} citation invalid"]}, []
            citation_id = citation.get(specification["citation_id_key"])
            if not isinstance(citation_id, str) or not citation_id or citation_id in citation_ids:
                return bindings, {"status": "invalid_ledger", "errors": ["citation ID missing/duplicate"]}, []
            citation_ids.add(citation_id)
        if row.get(specification["access_status_key"]) not in specification["collect_statuses"] and not citations:
            continue
        url = row.get(specification["url_key"])
        try:
            parsed = urlsplit(url) if isinstance(url, str) else None
            valid = parsed is not None and parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password
        except ValueError:
            valid = False
        selected.append({"source_id": source_id, "url": url, "citations": citations,
                         "status": "pending" if valid else "candidate_invalid",
                         "reason": None if valid else "source_url_not_public_http"})
    if len(selected) > specification["max_sources"]:
        raise ResearchSourceError("RESEARCH_SOURCE_BUDGET_INSUFFICIENT", "no silent source truncation")
    return bindings, {"status": "valid", "errors": []}, selected


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        elif not self.hidden and tag in {"p", "div", "br", "tr", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def project(path: Path, media_type: str) -> dict:
    """Extract full deterministic text; no inferred publication/history labels."""
    metadata: dict = {}
    if path.read_bytes()[:5] == b"%PDF-":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path), strict=True)
            if reader.is_encrypted:
                raise ValueError("encrypted PDF")
            records = [{"locator": {"page": index}, "text": page.extract_text() or ""}
                       for index, page in enumerate(reader.pages, 1)]
            metadata = {str(k): str(v) for k, v in (reader.metadata or {}).items()}
            package = Path(pypdf.__file__).parent
            code = [{"path": p.relative_to(package).as_posix(), "sha256": sha(p)}
                    for p in sorted(package.rglob("*")) if p.is_file()
                    and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".pyo"}]
            engine = {"name": "pypdf", "version": pypdf.__version__,
                      "module_sha256": sha(Path(pypdf.__file__)),
                      "package_sha256": hashlib.sha256(encoded(code)).hexdigest()}
        except Exception as exc:
            raise ResearchSourceError("RESEARCH_SOURCE_EXTRACTION_FAILED", str(exc)) from exc
    else:
        try:
            content = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise ResearchSourceError("RESEARCH_SOURCE_EXTRACTION_FAILED", "expected PDF or UTF-8 text") from exc
        if "html" in media_type or re.match(r"\s*(?:<!doctype\s+html|<html)", content, re.I):
            parser = _HtmlText()
            parser.feed(content)
            content = "".join(parser.parts)
            engine = {"name": "stdlib-html-text", "version": "1", "module_sha256": sha(Path(__file__))}
        elif not (media_type.startswith("text/") or media_type in {"application/json", "application/xml"}):
            raise ResearchSourceError("RESEARCH_SOURCE_EXTRACTION_UNSUPPORTED", media_type)
        else:
            engine = {"name": "utf8-text", "version": "1", "module_sha256": sha(Path(__file__))}
        records = [{"locator": {"record": 1}, "text": content}]
    if not records or not any(record["text"].strip() for record in records):
        raise ResearchSourceError("RESEARCH_SOURCE_EXTRACTION_FAILED", "empty text; scanned/dynamic content unsupported")
    return {"schema_version": PROJECTION_SCHEMA, "source_sha256": sha(path), "engine": engine,
            "complete": True, "records": records, "raw_metadata": metadata}


def projection_text(projection: dict) -> str:
    return "\n\n".join(
        f"[{next(iter(row['locator']))} {next(iter(row['locator'].values()))}]\n{row['text']}"
        for row in projection["records"]
    ) + "\n"


def _public_target(url: str) -> tuple[str, int, str, list[str]]:
    """Resolve once and pin a globally routable unicast address for this hop."""
    try:
        if not isinstance(url, str) or any(ord(char) <= 32 or ord(char) == 127 for char in url):
            raise ValueError("URL control/whitespace")
        parsed = urlsplit(url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower()
        if (parsed.scheme not in {"http", "https"} or not host or parsed.username is not None
                or parsed.password is not None or host.rstrip(".") == "localhost"
                or host.rstrip(".").endswith(".localhost")):
            raise ValueError("public HTTP URL required")
        port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
        if not 1 <= port <= 65535:
            raise ValueError("invalid public HTTP port")
        addresses = {ipaddress.ip_address(row[4][0])
                     for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not address.is_global or address.is_multicast or address.is_reserved
                                or address.is_unspecified for address in addresses):
            raise ValueError("non-public destination address")
        ordered = sorted(addresses, key=lambda address: (address.version != 4, str(address)))
        return host, port, str(ordered[0]), [str(address) for address in ordered]
    except (ValueError, UnicodeError, OSError) as exc:
        raise ResearchSourceError("RESEARCH_SOURCE_URL_NOT_PUBLIC", str(exc)) from exc


def _response_blocks(headers: Path, url: str, addresses: list[str], connected: str) -> list[dict]:
    blocks = []
    for block in re.split(r"\r?\n\r?\n", headers.read_text(encoding="iso-8859-1")):
        lines = block.strip().splitlines()
        if not lines or not lines[0].startswith("HTTP/"):
            continue
        fields = {}
        for line in lines[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                if key.lower() in {"location", "content-type", "date", "etag", "last-modified", "content-length"}:
                    fields[key.lower()] = value.strip()
        blocks.append({"url": url, "status": int(lines[0].split()[1]), "headers": fields,
                       "validated_addresses": addresses, "connected_address": connected})
    return blocks


def fetch(url: str, destination: Path, specification: dict, curl: Path | None = None) -> dict:
    """Trusted TLS, public DNS pinning and manually validated redirect hops.

    Proxies are disabled: a proxy's independent DNS resolution would evade the
    validated --resolve binding. Environments requiring a proxy fail explicitly.
    """
    executable = (curl or Path(shutil.which("curl") or "/missing-curl")).resolve()
    if not executable.is_file():
        raise ResearchSourceError("RESEARCH_SOURCE_FETCHER_UNAVAILABLE", "curl")
    headers = destination.with_name("headers.tmp")
    started = now()
    try:
        blocks, current_url = [], url
        for redirect_count in range(11):
            host, port, address, addresses = _public_target(current_url)
            parsed = urlsplit(current_url)
            authority = f"[{host}]" if ":" in host else host
            if parsed.port is not None:
                authority += f":{port}"
            network_url = urlunsplit((parsed.scheme, authority, parsed.path, parsed.query, ""))
            pinned_address = f"[{address}]" if ":" in address else address
            command = [str(executable), "-q", "--silent", "--show-error", "--noproxy", "*",
                       "--proto", "=http,https", "--max-time", str(specification["timeout_seconds"]),
                       "--connect-timeout", str(min(20, specification["timeout_seconds"])),
                       "--max-filesize", str(specification["max_bytes_per_source"]),
                       "--dump-header", str(headers), "--output", str(destination),
                       "--write-out", "%{http_code}\n%{url_effective}\n%{remote_ip}"]
            # Literal IPs already have no DNS resolution to pin.
            try:
                ipaddress.ip_address(host)
            except ValueError:
                command += ["--resolve", f"{host}:{port}:{pinned_address}"]
            command += ["--url", network_url]
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                       timeout=specification["timeout_seconds"] + 5, check=False)
            values = completed.stdout.splitlines()
            if completed.returncode or len(values) != 3 or not values[0].isdigit():
                raise ResearchSourceError("RESEARCH_SOURCE_ACQUISITION_FAILED", f"curl_exit={completed.returncode}: {completed.stderr[:1000].strip()}")
            if ipaddress.ip_address(values[2]) != ipaddress.ip_address(address):
                raise ResearchSourceError("RESEARCH_SOURCE_ADDRESS_DRIFT", "curl did not use the validated address")
            status = int(values[0])
            hop = _response_blocks(headers, current_url, addresses, values[2])
            if not hop or hop[-1]["status"] != status:
                raise ResearchSourceError("RESEARCH_SOURCE_RECEIPT_INVALID", "HTTP response headers")
            blocks.extend(hop)
            if status in {301, 302, 303, 307, 308} and hop[-1]["headers"].get("location"):
                if redirect_count == 10:
                    raise ResearchSourceError("RESEARCH_SOURCE_ACQUISITION_FAILED", "redirect limit")
                current_url = urljoin(current_url, hop[-1]["headers"]["location"])
                continue
            if not 200 <= status < 300 or not destination.is_file() or not destination.stat().st_size:
                raise ResearchSourceError("RESEARCH_SOURCE_ACQUISITION_FAILED", f"HTTP {status}")
            break
        if destination.stat().st_size > specification["max_bytes_per_source"]:
            raise ResearchSourceError("RESEARCH_SOURCE_BUDGET_INSUFFICIENT", "body bytes")
        version = subprocess.run([str(executable), "-q", "--version"], capture_output=True, text=True,
                                 encoding="utf-8", timeout=10, check=True).stdout.splitlines()[0]
        return {"requested_url": url, "final_url": values[1], "http_status": status,
                "redirect_count": redirect_count, "responses": blocks, "public_address_policy": "global-unicast-dns-pinned-no-proxy/v1",
                "media_type": blocks[-1]["headers"].get("content-type", "application/octet-stream").split(";", 1)[0].lower() if blocks else "application/octet-stream",
                "started_at": started, "finished_at": now(), "tls_verification": "curl-default-no-insecure",
                "fetcher": {"name": "curl", "path": str(executable), "version": version, "sha256": sha(executable)},
                "body_sha256": sha(destination), "body_size": destination.stat().st_size}
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        raise ResearchSourceError("RESEARCH_SOURCE_ACQUISITION_FAILED", str(exc)) from exc
    finally:
        headers.unlink(missing_ok=True)


def _bindings(root: Path, manifest: dict, specification: dict) -> dict:
    inputs, _, _ = _candidate_inputs(root, manifest, specification)
    return {"candidate_sha256": manifest["digests"]["candidate_original_sha256"],
            "policy_sha256": sha(within(within(root, manifest["paths"]["gt"]), POLICY_PATH)),
            "deliverables": inputs}


def _seal_lock(root: Path, manifest: dict, specification: dict, parent: dict | None = None) -> dict:
    bundle = within(root, BUNDLE_PATH)
    document = read(bundle / "manifest.json")
    lock = {"schema_version": LOCK_SCHEMA, "identity": manifest["identity"],
            "attempt_manifest_sha256": sha(root / "attempt-manifest.json"),
            "bindings": _bindings(root, manifest, specification), "bundle_path": BUNDLE_PATH,
            "bundle_manifest_sha256": sha(bundle / "manifest.json"), "entries": inventory(bundle),
            "acquisition_identity": document["acquisition_identity"], "parent_lock": parent}
    write(root / LOCK_PATH, lock)
    for path in bundle.rglob("*"):
        # Original mode-aware GT inventories must retain their historical modes.
        # All capsule bytes remain covered by the outer immutable lock inventory.
        if path.relative_to(bundle).parts[0] == "origins":
            continue
        path.chmod(0o555 if path.is_dir() else 0o444)
    bundle.chmod(0o555)
    (root / LOCK_PATH).chmod(0o444)
    return lock


def _origin_identity(root: Path, relative: str) -> dict:
    manifest = read(root / "attempt-manifest.json")
    lock = read(root / LOCK_PATH)
    return {"path": relative, "identity": manifest["identity"],
            "attempt_manifest_sha256": sha(root / "attempt-manifest.json"),
            "lock_sha256": sha(root / LOCK_PATH),
            "bundle_manifest_sha256": lock["bundle_manifest_sha256"],
            "capsule_inventory_sha256": hashlib.sha256(encoded(inventory(root))).hexdigest()}


def _origin_reference(proof: Any) -> str:
    if not isinstance(proof, dict):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "origin proof must be an object")
    relative = proof.get("path")
    if not isinstance(relative, str) or not relative.startswith("origins/") or not relative.endswith("/attempt"):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "capsule path")
    return relative


def _provenance_origin(provenance: Any) -> str:
    if not isinstance(provenance, dict):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "provenance must be an object")
    relative = provenance.get("origin_path")
    if not isinstance(relative, str) or not relative:
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "provenance origin path")
    return relative


def _verify_origin(root: Path, proof: dict, attempt_verifier: Callable | None) -> Path:
    if attempt_verifier is None or _REUSE_DEPTH.get() >= 8:
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "trusted attempt verifier required; maximum lineage depth 8")
    relative = _origin_reference(proof)
    origin = within(root, relative)
    if proof != _origin_identity(origin, relative):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "origin identity or inventory drift")
    token = _REUSE_DEPTH.set(_REUSE_DEPTH.get() + 1)
    try:
        # Trusted current verifier reads frozen evidence; never import/run origin code.
        if not within(origin, LOCK_PATH).is_file():
            raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_REQUIRED", "origin has no successful collection lock")
        attempt_verifier(origin, require_runtime=False)
    finally:
        _REUSE_DEPTH.reset(token)
    return origin


def _reuse_candidates(root: Path, manifest: dict, paths: tuple[Path, ...],
                      attempt_verifier: Callable | None) -> list[Path]:
    origins = []
    forbidden = [within(root, manifest["paths"][key]).resolve()
                 for key in ("candidate_original", "gt", "runtime_workspace")]
    for value in paths:
        expanded = value.expanduser().absolute()
        if any(part.is_symlink() for part in (expanded, *expanded.parents)):
            raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "symlink origin")
        try:
            origin = expanded.resolve(strict=True)
        except OSError as exc:
            raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "missing/unreadable origin") from exc
        if (origin == root or origin in root.parents or root in origin.parents
                or any(origin == tree or tree in origin.parents for tree in forbidden)):
            raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "origin inside current input tree")
        if origin in origins:
            continue
        if attempt_verifier is None:
            raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "trusted attempt verifier required")
        if not within(origin, LOCK_PATH).is_file():
            raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_REQUIRED", "origin has no successful collection lock")
        attempt_verifier(origin, require_runtime=False)
        origins.append(origin)
    return origins


def _copy_origin(origin: Path, staging: Path, index: int, attempt_verifier: Callable) -> dict:
    relative = f"origins/origin-{index:04d}/attempt"
    capsule = staging / relative
    capsule.mkdir(parents=True)
    # Full original input/source capsule, without executable runtime or score state.
    # Preserve modes so the original GT's mode-aware frozen inventory still verifies.
    for name in ("candidate-original", "private", "trace", "attempt-manifest.json", LOCK_PATH):
        source = within(origin, name)
        if not source.exists():
            continue
        if source.is_dir():
            inventory(source)  # Reject links/special files before copy, not dereference.
            shutil.copytree(source, capsule / name)
        else:
            shutil.copy2(source, capsule / name)
    proof = _origin_identity(capsule, relative)
    _verify_origin(staging, proof, attempt_verifier)
    return proof


def _public_receipt(receipt: dict, source_id: str) -> None:
    """Validate historical public-address evidence without doing a new DNS lookup."""
    _validate_receipt(receipt, source_id)
    try:
        if receipt["public_address_policy"] != "global-unicast-dns-pinned-no-proxy/v1":
            raise ValueError("public address policy")
        for url in (receipt["requested_url"], receipt["final_url"],
                    *(row["url"] for row in receipt["responses"])):
            parsed = urlsplit(url)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or any(ord(char) <= 32 or ord(char) == 127 for char in url)
                    or parsed.hostname.rstrip(".").lower() == "localhost"
                    or parsed.hostname.rstrip(".").lower().endswith(".localhost")):
                raise ValueError("public HTTP URL")
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError("HTTP port")
            try:
                address = ipaddress.ip_address(parsed.hostname)
            except ValueError:
                pass
            else:
                if not address.is_global or address.is_multicast or address.is_reserved:
                    raise ValueError("non-public URL address")
        for response in receipt["responses"]:
            addresses = [ipaddress.ip_address(value) for value in response["validated_addresses"]]
            if (not addresses or any(not address.is_global or address.is_multicast or address.is_reserved
                                     or address.is_unspecified for address in addresses)
                    or ipaddress.ip_address(response["connected_address"]) not in addresses):
                raise ValueError("public DNS pinning")
    except (KeyError, TypeError, ValueError) as exc:
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", f"historical public receipt: {source_id}") from exc


def _snapshot_covers(origin: Path, old: dict, row: dict, specification: dict) -> bool:
    """Mechanical snapshot suitability, never a semantic-support verdict."""
    bundle = within(origin, BUNDLE_PATH)
    old_policy = read(bundle / "manifest.json")["policy"]
    if any(old_policy[key] != specification[key] for key in ("as_of_inclusive", "timezone")):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "different research cutoff/timezone")
    receipt = read(within(bundle, old.get("original_receipt_path", old["receipt_path"])))
    finished = datetime.fromisoformat(receipt["finished_at"].replace("Z", "+00:00"))
    if finished.astimezone(ZoneInfo(specification["timezone"])).date() <= date.fromisoformat(specification["as_of_inclusive"]):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "snapshot acquired before inclusive research cutoff ended")
    _public_receipt(receipt, row["source_id"])
    projection = read(within(bundle, old["projection_path"]))
    # Raw UTF-8 evidence includes metadata omitted by the body-text projector,
    # such as JSON-LD dates. Binary formats rely on their frozen projection.
    body = within(bundle, old["body_path"])
    evidence = [record["text"] for record in projection["records"]]
    evidence.append(json.dumps(projection.get("raw_metadata", {}), ensure_ascii=False))
    media_type = receipt["media_type"]
    payload = body.read_bytes()
    if (not payload.startswith(b"%PDF-") and (media_type.startswith("text/")
            or media_type in {"application/json", "application/xml", "application/xhtml+xml"})):
        try:
            raw = payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            pass  # Never discard invalid bytes to manufacture a text quote match.
        else:
            if not any(ord(char) < 32 and char not in "\t\r\n" for char in raw):
                evidence.append(raw)
    normalized = [re.sub(r"\s+", "", unescape(value)) for value in evidence]
    for citation in row["citations"]:
        quote = citation.get(specification["quote_key"])
        if isinstance(quote, str) and quote.strip():
            needle = re.sub(r"\s+", "", unescape(quote))
            if not any(needle in value for value in normalized):
                return False
    return True


def _reuse_source(staging: Path, folder: Path, row: dict, old: dict,
                  origin: Path, proof: dict, specification: dict) -> None:
    old_bundle = within(origin, BUNDLE_PATH)
    original_receipt = within(old_bundle, old.get("original_receipt_path", old["receipt_path"]))
    receipt = read(original_receipt)
    _public_receipt(receipt, row["source_id"])
    if receipt["requested_url"] != row["url"] or old["url"] != row["url"]:
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "exact requested URL required")
    body = within(old_bundle, old["body_path"])
    if body.stat().st_size > specification["max_bytes_per_source"]:
        raise ResearchSourceError("RESEARCH_SOURCE_BUDGET_INSUFFICIENT", "reused body bytes")
    relative = folder.relative_to(staging).as_posix()
    for key, name in (("body_path", body.name), ("projection_path", "text.json"), ("text_path", "text.txt")):
        shutil.copy2(within(old_bundle, old[key]), folder / name)
        row[key] = f"{relative}/{name}"
    shutil.copy2(original_receipt, folder / "original-response.json")
    provenance = {"kind": "verified_snapshot_reuse", "origin_path": proof["path"],
                  "prior_identity": proof["identity"],
                  "prior_attempt_manifest_sha256": proof["attempt_manifest_sha256"],
                  "prior_lock_sha256": proof["lock_sha256"],
                  "prior_bundle_manifest_sha256": proof["bundle_manifest_sha256"],
                  "prior_source_id": old["source_id"],
                  "prior_source_sha256": hashlib.sha256(encoded(old)).hexdigest(),
                  "prior_receipt_sha256": old["receipt_sha256"],
                  "original_receipt_sha256": sha(original_receipt),
                  "projection_kind": "verified_frozen_origin_bytes", "reused_at": now()}
    row.update({key: old[key] for key in ("body_sha256", "projection_sha256", "text_sha256", "media_type", "final_url")})
    row.update({"status": "acquired", "source_path": relative, "provenance": provenance,
                "original_receipt_path": f"{relative}/original-response.json", "receipt_path": f"{relative}/response.json"})
    # This is a reuse event, deliberately not an HTTP receipt with new GET times.
    write(folder / "response.json", {"schema_version": REUSE_SCHEMA, "provenance": provenance,
          "collector_sha256": sha(Path(__file__)),
          "requested_url": row["url"], "final_url": row["final_url"], "media_type": row["media_type"],
          "body_sha256": row["body_sha256"], "body_size": body.stat().st_size,
          "original_receipt_path": row["original_receipt_path"],
          "original_receipt_sha256": sha(original_receipt)})
    row["receipt_sha256"] = sha(folder / "response.json")


def collect(root: Path, *, curl: Path | None = None,
            fetcher: Callable | None = None, reuse_sources_from: tuple[Path, ...] = (),
            attempt_verifier: Callable | None = None) -> dict:
    """Called only after the outer entrypoint verifies the original attempt."""
    manifest = read(root / "attempt-manifest.json")
    specification = policy(root, manifest)
    if specification is None:
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_REQUIRED")
    if (root / LOCK_PATH).exists() or (root / BUNDLE_PATH).exists():
        raise ResearchSourceError("RESEARCH_SOURCE_COLLECTION_EXISTS")
    if any((root / name).exists() for name in ("worker", "semantic", "score.json")):
        raise ResearchSourceError("RESEARCH_SOURCE_COLLECTION_TOO_LATE")
    inputs, input_status, selected = _candidate_inputs(root, manifest, specification)
    origins = _reuse_candidates(root, manifest, reuse_sources_from, attempt_verifier)
    parent = root / "private"
    parent.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".research-sources-", dir=parent))
    try:
        proofs, matches = [], {}
        for origin in origins:
            old_document = read(within(origin, BUNDLE_PATH) / "manifest.json")
            for old in old_document["sources"]:
                if old["status"] == "acquired":
                    matches.setdefault(old["url"], (origin, old))
        used = {}
        for index, row in enumerate(selected, 1):
            if row["status"] == "candidate_invalid":
                continue
            relative = f"sources/source-{index:04d}"
            folder = staging / relative
            folder.mkdir(parents=True)
            match = matches.get(row["url"])
            if match is not None and _snapshot_covers(match[0], match[1], row, specification):
                origin, old = match
                if origin not in used:
                    used[origin] = _copy_origin(origin, staging, len(used) + 1, attempt_verifier)
                    proofs.append(used[origin])
                # Use the verified copied capsule, preventing a later original-path dependency.
                capsule = within(staging, used[origin]["path"])
                old = next(value for value in read(capsule / BUNDLE_PATH / "manifest.json")["sources"]
                           if value["source_id"] == old["source_id"])
                _reuse_source(staging, folder, row, old, capsule, used[origin], specification)
                continue
            body = folder / "body.bin"
            receipt = (fetcher or fetch)(row["url"], body, specification, curl)
            if (not body.is_file() or receipt.get("body_sha256") != sha(body)
                    or receipt.get("body_size") != body.stat().st_size):
                raise ResearchSourceError("RESEARCH_SOURCE_RECEIPT_INVALID", row["source_id"])
            projection = project(body, receipt["media_type"])
            suffix = ".pdf" if body.read_bytes()[:5] == b"%PDF-" else ".html" if "html" in receipt["media_type"] else ".txt"
            target = body.with_name("body" + suffix)
            body.rename(target)
            receipt["collector_sha256"] = sha(Path(__file__))
            write(folder / "response.json", receipt)
            write(folder / "text.json", projection)
            (folder / "text.txt").write_text(projection_text(projection), encoding="utf-8", newline="\n")
            row.update({"status": "acquired", "source_path": relative, "body_path": f"{relative}/{target.name}",
                        "body_sha256": sha(target), "text_path": f"{relative}/text.txt",
                        "text_sha256": sha(folder / "text.txt"), "projection_path": f"{relative}/text.json",
                        "projection_sha256": sha(folder / "text.json"),
                        "receipt_path": f"{relative}/response.json", "media_type": receipt["media_type"],
                        "receipt_sha256": sha(folder / "response.json"),
                        "final_url": receipt["final_url"]})
        document = {"schema_version": BUNDLE_SCHEMA, "acquisition_identity": manifest["identity"],
                    "created_at": now(), "bindings": _bindings(root, manifest, specification),
                    "policy": specification, "candidate_input_status": input_status["status"],
                    "errors": input_status["errors"], "sources": selected,
                    "collector_sha256": sha(Path(__file__)),
                    "collector_python": {"version": sys.version.split()[0], "executable_sha256": sha(Path(sys.executable).resolve())},
                    "historical_publication_verified": False,
                    "reuse_origins": proofs,
                    "acquisition_summary": {"fresh_get_count": sum(row["status"] == "acquired" and "provenance" not in row for row in selected),
                                            "reused_snapshot_count": sum("provenance" in row for row in selected)}}
        write(staging / "manifest.json", document)
        staging.rename(root / BUNDLE_PATH)
        lock = _seal_lock(root, manifest, specification)
        return {"status": "PASS", "bundle_path": BUNDLE_PATH, "lock_path": LOCK_PATH,
                "bundle_manifest_sha256": lock["bundle_manifest_sha256"],
                "candidate_input_status": input_status["status"],
                "acquired_count": sum(row["status"] == "acquired" for row in selected),
                **document["acquisition_summary"]}
    except BaseException as exc:
        # Failure audits are separate from the immutable successful bundle/lock.
        if isinstance(exc, ResearchSourceError):
            failure = root / ("research-source-failure-" + staging.name.rsplit("-", 1)[-1] + ".json")
            write(failure, {"at": now(), "identity": manifest["identity"], "code": exc.code,
                            "detail": exc.detail, "bindings": {"deliverables": inputs}})
        raise
    finally:
        if staging.exists():
            # Copied frozen capsules contain read-only directories. Only mutate
            # our unpublished temporary copy, never the selected original.
            for path in (staging, *staging.rglob("*")):
                if path.is_dir() and not path.is_symlink():
                    path.chmod(0o755)
            shutil.rmtree(staging)


def _check_parent(lock: dict, manifest: dict, depth: int = 0) -> None:
    parent = lock.get("parent_lock")
    if parent is None:
        if lock.get("acquisition_identity") != lock.get("identity"):
            raise ResearchSourceError("RESEARCH_SOURCE_LINEAGE_INVALID", "acquisition identity")
        return
    if depth > 20 or not isinstance(parent, dict):
        raise ResearchSourceError("RESEARCH_SOURCE_LINEAGE_INVALID")
    for key in ("bindings", "bundle_manifest_sha256", "entries", "acquisition_identity", "bundle_path"):
        if parent.get(key) != lock.get(key):
            raise ResearchSourceError("RESEARCH_SOURCE_LINEAGE_INVALID", key)
    if depth == 0:
        lineage = manifest.get("lineage") or {}
        if (lineage.get("source_attempt_manifest_sha256") != parent.get("attempt_manifest_sha256")
                or lineage.get("source_scoring_attempt_id") != parent.get("identity", {}).get("scoring_attempt_id")):
            raise ResearchSourceError("RESEARCH_SOURCE_LINEAGE_INVALID", "rescore origin")
    _check_parent(parent, manifest, depth + 1)


def _validate_receipt(receipt: dict, source_id: str) -> None:
    try:
        started = datetime.fromisoformat(receipt["started_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(receipt["finished_at"].replace("Z", "+00:00"))
        responses = receipt["responses"]
        fetcher = receipt["fetcher"]
        valid = (started.utcoffset() == finished.utcoffset() == timezone.utc.utcoffset(started)
                 and started <= finished and 200 <= receipt["http_status"] < 300
                 and receipt["tls_verification"] == "curl-default-no-insecure"
                 and isinstance(responses, list) and bool(responses)
                 and responses[-1]["status"] == receipt["http_status"]
                 and sum(300 <= row["status"] < 400 for row in responses) == receipt["redirect_count"]
                 and fetcher["name"] == "curl" and bool(fetcher["version"])
                 and bool(re.fullmatch(r"[0-9a-f]{64}", fetcher["sha256"])))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ResearchSourceError("RESEARCH_SOURCE_RECEIPT_INVALID", source_id)


def _verify_reused_source(bundle: Path, row: dict, receipt: dict, origins: dict, collector_sha256: str) -> tuple[dict, str]:
    provenance = row["provenance"]
    origin_path = _provenance_origin(provenance)
    if provenance.get("kind") != "verified_snapshot_reuse" or origin_path not in origins:
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "provenance")
    origin, proof = origins[origin_path]
    old_document = read(origin / BUNDLE_PATH / "manifest.json")
    candidates = [old for old in old_document["sources"] if old.get("source_id") == provenance.get("prior_source_id")]
    if len(candidates) != 1:
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "prior source identity")
    old = candidates[0]
    old_bundle = origin / BUNDLE_PATH
    if not _snapshot_covers(origin, old, row, read(bundle / "manifest.json")["policy"]):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "new citation not covered by original snapshot")
    original_path = within(old_bundle, old.get("original_receipt_path", old["receipt_path"]))
    expected_provenance = {"kind": "verified_snapshot_reuse", "origin_path": proof["path"],
            "prior_identity": proof["identity"], "prior_attempt_manifest_sha256": proof["attempt_manifest_sha256"],
            "prior_lock_sha256": proof["lock_sha256"], "prior_bundle_manifest_sha256": proof["bundle_manifest_sha256"],
            "prior_source_id": old["source_id"], "prior_source_sha256": hashlib.sha256(encoded(old)).hexdigest(),
            "prior_receipt_sha256": old["receipt_sha256"], "original_receipt_sha256": sha(original_path),
            "projection_kind": "verified_frozen_origin_bytes", "reused_at": provenance.get("reused_at")}
    original = read(within(bundle, row["original_receipt_path"]))
    _public_receipt(original, row["source_id"])
    expected_receipt = {"schema_version": REUSE_SCHEMA, "provenance": expected_provenance,
            "collector_sha256": collector_sha256,
            "requested_url": row["url"], "final_url": row["final_url"], "media_type": row["media_type"],
            "body_sha256": row["body_sha256"], "body_size": original["body_size"],
            "original_receipt_path": row["original_receipt_path"], "original_receipt_sha256": sha(original_path)}
    if not isinstance(provenance.get("reused_at"), str):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "reused_at must be a UTC timestamp string")
    try:
        reused_at = datetime.fromisoformat(provenance["reused_at"].replace("Z", "+00:00"))
        finished = datetime.fromisoformat(original["finished_at"].replace("Z", "+00:00"))
        time_valid = reused_at.utcoffset() == timezone.utc.utcoffset(reused_at) and reused_at >= finished
    except (KeyError, TypeError, ValueError):
        time_valid = False
    if (provenance != expected_provenance or receipt != expected_receipt or not time_valid
            or old.get("status") != "acquired" or row["url"] != old["url"]
            or any(row.get(key) != old.get(key) for key in ("body_sha256", "projection_sha256", "text_sha256", "media_type", "final_url"))
            or sha(within(bundle, row["original_receipt_path"])) != sha(original_path)):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "source/receipt lineage drift")
    return original, original["collector_sha256"]


def _verify(root: Path, *, required: bool = False, archived: bool = False,
            attempt_verifier: Callable | None = None) -> dict | None:
    manifest = read(root / "attempt-manifest.json")
    specification = policy(root, manifest)
    lock_path = within(root, LOCK_PATH)
    if specification is None:
        if lock_path.exists() or (root / BUNDLE_PATH).exists():
            raise ResearchSourceError("RESEARCH_SOURCE_POLICY_REQUIRED")
        return None
    if not lock_path.is_file():
        if required or (root / BUNDLE_PATH).exists():
            raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_REQUIRED")
        return None
    lock = read(lock_path)
    if (lock.get("schema_version") != LOCK_SCHEMA or lock.get("identity") != manifest["identity"]
            or lock.get("attempt_manifest_sha256") != sha(root / "attempt-manifest.json")
            or lock.get("bindings") != _bindings(root, manifest, specification)
            or lock.get("bundle_path") != BUNDLE_PATH):
        raise ResearchSourceError("RESEARCH_SOURCE_LOCK_INVALID", "attempt/input binding")
    _check_parent(lock, manifest)
    bundle = within(root, BUNDLE_PATH)
    if not bundle.is_dir() or lock.get("entries") != inventory(bundle) or lock.get("bundle_manifest_sha256") != sha(bundle / "manifest.json"):
        raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_DRIFT")
    document = read(bundle / "manifest.json")
    inputs, input_status, selected = _candidate_inputs(root, manifest, specification)
    if (document.get("schema_version") != BUNDLE_SCHEMA or document.get("policy") != specification
            or document.get("bindings") != lock["bindings"]
            or document.get("acquisition_identity") != lock.get("acquisition_identity")
            or document.get("candidate_input_status") != input_status["status"]
            or document.get("errors") != input_status["errors"]
            or not isinstance(document.get("sources"), list) or len(document["sources"]) != len(selected)
            or not all(isinstance(row, dict) for row in document["sources"])):
        raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_INVALID")
    if not archived and document.get("collector_sha256") != sha(Path(__file__)):
        raise ResearchSourceError("RESEARCH_SOURCE_COLLECTOR_DRIFT")
    proofs = document.get("reuse_origins", [])
    if not isinstance(proofs, list):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "reuse_origins must be an array")
    origins = {}
    for proof in proofs:
        relative = _origin_reference(proof)
        if relative in origins:
            raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "duplicate origin")
        origins[relative] = (_verify_origin(bundle, proof, attempt_verifier), proof)
    provenance_paths = {_provenance_origin(row["provenance"]) for row in document["sources"] if "provenance" in row}
    reused_count = sum("provenance" in row for row in document["sources"])
    summary = {"fresh_get_count": sum(row["status"] == "acquired" for row in document["sources"]) - reused_count,
               "reused_snapshot_count": reused_count}
    if (document.get("acquisition_summary", summary) != summary
            or bool(origins) != bool(reused_count)
            or set(origins) != provenance_paths):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "acquisition summary/origins")
    for expected, row in zip(selected, document["sources"]):
        if any(row.get(key) != expected[key] for key in ("source_id", "url", "citations", "reason")):
            raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_INVALID", "ledger source binding")
        if expected["status"] == "candidate_invalid":
            if row.get("status") != "candidate_invalid":
                raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_INVALID", "candidate status")
            continue
        if row.get("status") != "acquired":
            raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_REQUIRED", "source not acquired")
        body = within(bundle, row["body_path"])
        receipt = read(within(bundle, row["receipt_path"]))
        expected_collector = document["collector_sha256"]
        reused = "provenance" in row
        if reused:
            receipt, expected_collector = _verify_reused_source(bundle, row, receipt, origins, document["collector_sha256"])
        else:
            _validate_receipt(receipt, row["source_id"])
        projection = read(within(bundle, row["projection_path"]))
        text = within(bundle, row["text_path"])
        if (row.get("body_sha256") != sha(body) or receipt.get("body_sha256") != sha(body)
                or row.get("receipt_sha256") != sha(within(bundle, row["receipt_path"]))
                or row.get("projection_sha256") != sha(within(bundle, row["projection_path"]))
                or body.stat().st_size > specification["max_bytes_per_source"]
                or receipt.get("body_size") != body.stat().st_size or receipt.get("requested_url") != row["url"]
                or receipt.get("final_url") != row.get("final_url") or receipt.get("media_type") != row.get("media_type")
                or receipt.get("collector_sha256") != expected_collector
                or projection.get("schema_version") != PROJECTION_SCHEMA or projection.get("source_sha256") != sha(body)
                or projection.get("complete") is not True or row.get("text_sha256") != sha(text)
                or text.read_text(encoding="utf-8") != projection_text(projection)):
            raise ResearchSourceError("RESEARCH_SOURCE_RECEIPT_INVALID", row["source_id"])
        # Archive mode trusts the frozen extraction receipt; it does not require
        # curl/pypdf on the replay host or claim to re-run acquisition/extraction.
        if not archived and not reused and projection != project(body, row["media_type"]):
            raise ResearchSourceError("RESEARCH_SOURCE_PROJECTION_DRIFT", row["source_id"])
    references = [{"type": "research_source_lock", "path": LOCK_PATH, "sha256": sha(lock_path)}]
    references += [{"type": "independent_research_source", "path": f"{BUNDLE_PATH}/{row['path']}", "sha256": row["sha256"]}
                   for row in lock["entries"] if not row["path"].startswith("origins/")]
    return {"path": BUNDLE_PATH, "manifest_sha256": lock["bundle_manifest_sha256"],
            "lock_path": LOCK_PATH, "lock_sha256": sha(lock_path), "references": references,
            "candidate_input_status": document["candidate_input_status"]}


def verify(root: Path, *, required: bool = False, archived: bool = False,
           attempt_verifier: Callable | None = None) -> dict | None:
    try:
        return _verify(root, required=required, archived=archived, attempt_verifier=attempt_verifier)
    except ResearchSourceError:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        raise ResearchSourceError("RESEARCH_SOURCE_BUNDLE_INVALID", str(exc)) from exc


def copy_for_rescore(source: Path, target: Path, *, attempt_verifier: Callable | None = None) -> None:
    binding = verify(source, required=True, attempt_verifier=attempt_verifier)
    if binding is None:
        return
    source_lock = read(source / LOCK_PATH)
    shutil.copytree(source / BUNDLE_PATH, target / BUNDLE_PATH)
    manifest = read(target / "attempt-manifest.json")
    specification = policy(target, manifest)
    _seal_lock(target, manifest, specification, source_lock)
    verify(target, required=True, attempt_verifier=attempt_verifier)
