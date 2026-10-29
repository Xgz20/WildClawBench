"""Trusted private-policy dispatch. Never load backend code from an attempt."""
from __future__ import annotations

import json
from pathlib import Path

import research_sources as v1


def backend(root: Path):
    manifest = v1.read(root / "attempt-manifest.json")
    contract = v1.read(v1.within(root, manifest["paths"]["contract"]))
    requirements = contract.get("scoring_runtime") or {}
    if not isinstance(requirements, dict):
        raise v1.ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "scoring_runtime")
    if not requirements.get("research_sources"):
        return v1
    if requirements["research_sources"] is not True:
        raise v1.ResearchSourceError("RESEARCH_SOURCE_POLICY_INVALID", "research_sources must be boolean")
    private_gt = v1.within(root, manifest["paths"]["gt"])
    schema = v1.read(v1.within(private_gt, v1.POLICY_PATH)).get("schema_version")
    if schema == v1.POLICY_SCHEMA:
        lock_path = root / v1.LOCK_PATH
        if lock_path.is_file():
            import research_sources_proxy as proxy
            if v1.read(lock_path).get("schema_version") == proxy.LOCK_SCHEMA:
                return proxy
        return v1
    if schema == "wildclawbench.research-source-policy/v2":
        import research_sources_native as v2
        return v2
    raise v1.ResearchSourceError("RESEARCH_SOURCE_POLICY_UNSUPPORTED", str(schema))


def verify(root: Path, **kwargs):
    return backend(root).verify(root, **kwargs)


def collect(root: Path, *, reuse_sources_from: tuple[Path, ...] = (), **kwargs):
    current = backend(root)
    explicit_proxy = kwargs.pop("trusted_http_connect_proxy", None)
    import research_sources_proxy as proxy
    if explicit_proxy is not None:
        if current not in (v1, proxy):
            raise v1.ResearchSourceError("RESEARCH_SOURCE_TRANSPORT_UNSUPPORTED", "explicit HTTP CONNECT currently supports policy v1 only")
        proxy.proxy_endpoint(explicit_proxy)
        current = proxy
    if current is proxy:
        kwargs["trusted_http_connect_proxy"] = explicit_proxy
    manifest = current.read(root / "attempt-manifest.json")
    policy = current.policy(root, manifest)
    # Policy/stage/input errors precede origin admission in both collectors.
    # Let the selected original lifecycle report those errors itself rather than
    # masking them with an invalid reuse path during compatibility dispatch.
    if (policy is None or (root / current.LOCK_PATH).exists()
            or (root / current.BUNDLE_PATH).exists()
            or any((root / name).exists() for name in ("worker", "semantic", "score.json"))):
        return current.collect(root, reuse_sources_from=reuse_sources_from, **kwargs)
    current._candidate_inputs(root, manifest, policy)
    # Preserve the v1 admission order and typed errors: reject missing, linked,
    # overlapping or unlocked origins before opening any origin policy/manifest.
    # The frozen verifier also checks complete prior inputs and source inventories
    # before their policy is eligible to select a backend. The collector repeats
    # its own admission check; no legacy protection is bypassed or weakened.
    origins = v1._reuse_candidates(root, manifest, reuse_sources_from,
                                   kwargs.get("attempt_verifier"))
    for origin in origins:
        other = backend(origin)
        old = other.policy(origin, other.read(origin / "attempt-manifest.json"))
        compatible = other is current or current is proxy and other is v1
        if (not compatible or policy is None or old is None
                or old.get("projection_profile") != policy.get("projection_profile")):
            raise v1.ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "incompatible source policy/profile")
    return current.collect(root, reuse_sources_from=reuse_sources_from, **kwargs)


def copy_for_rescore(source: Path, target: Path, **kwargs):
    current = backend(source)
    target_backend = backend(target)
    import research_sources_proxy as proxy
    compatible = target_backend is current or current is proxy and target_backend is v1
    if (not compatible or current.policy(source, current.read(source / "attempt-manifest.json"))
            != target_backend.policy(target, target_backend.read(target / "attempt-manifest.json"))):
        raise v1.ResearchSourceError("RESEARCH_SOURCE_REUSE_INVALID", "rescore source policy changed")
    return current.copy_for_rescore(source, target, **kwargs)


def required_api_paths(root: Path, binding: dict) -> set[str]:
    paths = {v1.LOCK_PATH, f"{v1.BUNDLE_PATH}/manifest.json"}
    paths.update(row["path"] for row in binding["references"]
                 if row["path"].endswith(("/text.txt", "/response.json", "/original-response.json")))
    if backend(root).PROJECTION_SCHEMA != v1.PROJECTION_SCHEMA:
        document = v1.read(root / v1.BUNDLE_PATH / "manifest.json")
        paths.update(f"{v1.BUNDLE_PATH}/{row['projection_path']}" for row in document["sources"]
                     if row["status"] == "acquired")
    return paths


def frozen_file_view(root: Path, path: Path, expected_sha: str | None, *,
                     record_offset: int = 0, record_limit: int | None = None,
                     max_chars: int = 4_000_000) -> dict | None:
    """V2 source originals use their verified frozen projection, not a new parser.

    Caller first verifies the attempt/source binding. Hashes are checked again
    here to avoid substituting a different file during evidence construction.
    Candidate Office artifacts and every v1 path retain the old native helper.
    """
    if backend(root).PROJECTION_SCHEMA == v1.PROJECTION_SCHEMA:
        return None
    bundle = root / v1.BUNDLE_PATH
    document = v1.read(bundle / "manifest.json")
    try:
        relative = path.relative_to(bundle).as_posix()
    except ValueError:
        return None
    matches = [r for r in document["sources"] if r.get("body_path") == relative and r["status"] == "acquired"]
    if not matches:
        return None
    if len(matches) != 1:
        raise v1.ResearchSourceError("RESEARCH_SOURCE_PROJECTION_INVALID", "ambiguous source original")
    row = matches[0]
    projection_path = v1.within(bundle, row["projection_path"])
    if (v1.sha(path) != row["body_sha256"] or expected_sha not in {None,row["body_sha256"]}
            or v1.sha(projection_path) != row["projection_sha256"]):
        raise v1.ResearchSourceError("RESEARCH_SOURCE_PROJECTION_INVALID", "original/projection digest")
    projection = v1.read(projection_path)
    current = backend(root)
    from native_source_projection import validate_projection
    validate_projection(projection, path, current.policy(root, current.read(root / "attempt-manifest.json")))
    all_rows = projection["records"]
    selected = all_rows[record_offset:] if record_limit is None else all_rows[record_offset:record_offset+record_limit]
    text = "\n".join(json.dumps(r,ensure_ascii=False,sort_keys=True) for r in selected)
    included = text[:max_chars]
    return {"schema_version":projection["schema_version"], "profile":projection["profile"],
            "source_sha256":row["body_sha256"], "source_projection_sha256":row["projection_sha256"],
            "content_representation":"verified_frozen_source_records", "format":projection["format"],
            "text":included, "original_chars":len(text), "included_chars":len(included),
            "truncated":len(included)<len(text), "record_offset":record_offset,
            "record_count":len(all_rows), "selected_record_count":len(selected),
            "engine":projection["engine"], "limitations":projection["limitations"]}
