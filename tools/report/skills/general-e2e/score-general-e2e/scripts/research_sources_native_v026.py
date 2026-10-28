"""Version 2 public-source collection, retaining native Office source evidence.

The v1 collector remains byte-frozen. This backend has its own schemas and identity.

The collector is trusted scoring infrastructure. Hashes prove the frozen receipt
chain, not internet provenance on their own. It never supplies business scores,
historical publication dates, or semantic support labels.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from html import unescape
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import sys
import tempfile
from typing import Callable
from zoneinfo import ZoneInfo

from native_source_projection import (PROFILE, DEFAULT_LIMITS, project, identify, projection_text)
import native_source_projection as projection_module


POLICY_SCHEMA = "wildclawbench.research-source-policy/v2"
BUNDLE_SCHEMA = "wildclawbench.research-source-bundle/v2"
LOCK_SCHEMA = "wildclawbench.research-source-lock/v2"
PROJECTION_SCHEMA = "wildclawbench.research-source-text/v2"
BUNDLE_PATH = "private/research-sources"
LOCK_PATH = "research-sources.lock.json"
POLICY_PATH = "research_source_policy.json"
REUSE_SCHEMA = "wildclawbench.research-source-reuse-receipt/v2"
POLICY_DEFAULTS = {
    "sources_key": "sources", "source_id_key": "source_id", "url_key": "url",
    "access_status_key": "access_status", "collect_statuses": ["read_full", "read_excerpt"],
    "citations_key": "citations", "citation_id_key": "citation_id",
    "quote_key": "quote", "locator_key": "locator", "max_sources": 40,
    "max_bytes_per_source": 20 * 1024 * 1024, "timeout_seconds": 60, "projection_profile": PROFILE,
    "allowed_formats": ["pdf", "html", "utf8", "docx", "xlsx"], **DEFAULT_LIMITS,
}


import research_sources as legacy
from research_sources import ResearchSourceError

_bindings = legacy._bindings
_candidate_inputs = legacy._candidate_inputs
_check_parent = legacy._check_parent
_copy_origin = legacy._copy_origin
_origin_identity = legacy._origin_identity
_origin_reference = legacy._origin_reference
_provenance_origin = legacy._provenance_origin
_public_receipt = legacy._public_receipt
_public_target = legacy._public_target
_response_blocks = legacy._response_blocks
_reuse_candidates = legacy._reuse_candidates
_validate_receipt = legacy._validate_receipt


_verify_origin = legacy._verify_origin
encoded = legacy.encoded
fetch = legacy.fetch
inventory = legacy.inventory
now = legacy.now
read = legacy.read
sha = legacy.sha
within = legacy.within
write = legacy.write


def _collector_components() -> dict:
    return {"legacy_helpers_sha256": sha(Path(legacy.__file__)),
            "projector_sha256": sha(Path(projection_module.__file__))}

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
    required = {"schema_version", "ledger_path", "deliverable_paths", "as_of_inclusive", "timezone", "projection_profile"}
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
    if result["projection_profile"] != PROFILE:
        raise ResearchSourceError("RESEARCH_SOURCE_PROFILE_UNSUPPORTED", str(result["projection_profile"]))
    formats = result["allowed_formats"]
    if (not isinstance(formats, list) or not formats
            or any(not isinstance(value, str) or value not in {"pdf", "html", "utf8", "docx", "xlsx"} for value in formats)
            or len(set(formats)) != len(formats)):
        raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "allowed_formats")
    for key, maximum in DEFAULT_LIMITS.items():
        if type(result[key]) is not int or not 1 <= result[key] <= maximum:
            raise ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", key)
    return result


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


def _snapshot_covers(origin: Path, old: dict, row: dict, specification: dict) -> bool:
    """Mechanical snapshot suitability, never a semantic-support verdict."""
    bundle = within(origin, BUNDLE_PATH)
    old_policy = read(bundle / "manifest.json")["policy"]
    if (old_policy.get("schema_version") != POLICY_SCHEMA
            or old_policy.get("projection_profile") != specification["projection_profile"]):
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "incompatible projection profile")
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
    projection_module.validate_projection(projection, body, specification)
    if projection.get("format") in {"docx", "xlsx"} and any(
            old_policy[key] > specification[key] for key in DEFAULT_LIMITS
            if key not in {"max_projection_chars", "max_native_records"}):
        # The immutable extraction receipt does not certify arbitrary tighter
        # parser limits. Do not reinterpret/reextract it during a reuse event.
        raise ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "native snapshot has looser extraction limits; collect fresh explicitly")
    evidence = [record["text"] for record in projection["records"]]
    if projection.get("format") not in {"docx", "xlsx"}:
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
            kind = identify(body, receipt["media_type"], specification,
                            urls=(row["url"], receipt["final_url"]))
            suffix = {"utf8": ".txt"}.get(kind, "." + kind)
            target = body.with_name("body" + suffix)
            body.rename(target)
            projection = project(target, receipt["media_type"], specification)
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
                    "collector_components": _collector_components(),
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
    components = document.get("collector_components")
    if (not isinstance(components, dict) or set(components) != set(_collector_components())
            or any(not isinstance(value,str) or re.fullmatch(r"[0-9a-f]{64}",value) is None for value in components.values())
            or not archived and components != _collector_components()):
        raise ResearchSourceError("RESEARCH_SOURCE_COLLECTOR_DRIFT", "supporting code identity")
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
        from native_source_projection import validate_projection
        validate_projection(projection, body, specification)
        # Archive mode trusts the frozen extraction receipt; it does not require
        # curl/pypdf on the replay host or claim to re-run acquisition/extraction.
        if not archived and not reused and projection != project(body, row["media_type"], specification):
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
