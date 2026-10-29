"""Explicit trusted loopback HTTP CONNECT backend for the unchanged v1 private policy.
The frozen direct collector is imported only from this trusted installed package.
Transport identity is distinct; proxy TCP peer is never an observed origin socket.
"""
from __future__ import annotations
from datetime import date, datetime, timezone
from html import unescape
import hashlib, ipaddress, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
import research_sources as legacy
from research_sources import ResearchSourceError
POLICY_SCHEMA = legacy.POLICY_SCHEMA
BUNDLE_SCHEMA = 'wildclawbench.research-source-bundle/trusted-http-connect-v1'
LOCK_SCHEMA = 'wildclawbench.research-source-lock/trusted-http-connect-v1'
REUSE_SCHEMA = 'wildclawbench.research-source-reuse-receipt/trusted-http-connect-v1'
PROJECTION_SCHEMA = legacy.PROJECTION_SCHEMA
BUNDLE_PATH, LOCK_PATH, POLICY_PATH = legacy.BUNDLE_PATH, legacy.LOCK_PATH, legacy.POLICY_PATH
_bindings = legacy._bindings
_candidate_inputs = legacy._candidate_inputs
_check_parent = legacy._check_parent
_copy_origin = legacy._copy_origin
_origin_identity = legacy._origin_identity
_origin_reference = legacy._origin_reference
_provenance_origin = legacy._provenance_origin
_public_target = legacy._public_target
_reuse_candidates = legacy._reuse_candidates
_verify_origin = legacy._verify_origin
encoded = legacy.encoded
inventory = legacy.inventory
now = legacy.now
read = legacy.read
sha = legacy.sha
within = legacy.within
write = legacy.write
policy = legacy.policy
project = legacy.project
projection_text = legacy.projection_text

def _collector_components() -> dict:
    return {'legacy_helpers_sha256': sha(Path(legacy.__file__)), 'transport_protocol': TRANSPORT_SCHEMA}



# Production transport code, combined with a frozen v1 lifecycle at build time.
TRANSPORT_SCHEMA = 'wildclawbench.research-source-http-connect-receipt/v1'
ADDRESS_POLICY = 'validated-public-ip-connect-target-trusted-local-http-proxy/v1'
LEGACY_COLLECTOR_SHA256 = '4fcb5239474bf5d3749f817abdccd02054ba86e2d766458f78f70d2da8c8968a'
TRUST_PROFILE = 'explicit-loopback-proxy-curl-default-trust-ca-env-cleared/v1'


def proxy_endpoint(value: str) -> dict:
    """Separate trust boundary: an explicit, credential-free loopback literal."""
    try:
        if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value):
            raise ValueError('proxy URL control/whitespace')
        parsed = urlsplit(value)
        if (parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', '::1'}
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or parsed.port is None or not 1 <= parsed.port <= 65535):
            raise ValueError('explicit HTTP loopback literal and port required')
        host = parsed.hostname
        canonical = f'http://[{host}]:{parsed.port}' if ':' in host else f'http://{host}:{parsed.port}'
        if value != canonical:
            raise ValueError('canonical proxy endpoint required')
        return {'url': canonical, 'address': host, 'port': parsed.port,
                'mode': 'trusted-local-http-connect', 'trust_profile': TRUST_PROFILE,
                'origin_socket_observed': False}
    except (ValueError, TypeError) as exc:
        raise ResearchSourceError('RESEARCH_SOURCE_PROXY_INVALID', str(exc)) from exc


def _network_url(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    if (not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value)
            or parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError('public HTTP URL required')
    host = parsed.hostname.encode('idna').decode('ascii').lower()
    if host.rstrip('.') == 'localhost' or host.rstrip('.').endswith('.localhost'):
        raise ValueError('localhost URL')
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == 'https' else 80)
    if not 1 <= port <= 65535:
        raise ValueError('invalid target port')
    authority = f'[{host}]' if ':' in host else host
    if parsed.port is not None:
        authority += f':{port}'
    return urlunsplit((parsed.scheme, authority, parsed.path or '/', parsed.query, '')), host, port


def _curl_environment() -> dict:
    import os
    return {k: v for k, v in os.environ.items()
            if not k.lower().endswith('_proxy')
            and k.upper() not in {'CURL_CA_BUNDLE', 'SSL_CERT_FILE', 'SSL_CERT_DIR',
                                  'REQUESTS_CA_BUNDLE', 'SSLKEYLOGFILE'}}


def _origin_response(headers: Path, url: str, status: int) -> dict:
    """CONNECT headers are suppressed by curl; never interpret them as origin."""
    blocks = []
    for raw in re.split(r'\r?\n\r?\n', headers.read_text(encoding='iso-8859-1')):
        lines = raw.strip().splitlines()
        if not lines or not lines[0].startswith('HTTP/'):
            continue
        parts = lines[0].split(None, 2)
        if len(parts) < 2 or not parts[1].isdigit() or 'connection established' in lines[0].lower():
            raise ResearchSourceError('RESEARCH_SOURCE_RECEIPT_INVALID', 'CONNECT/origin headers not separated')
        fields = {}
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                if key.lower() in {'location', 'content-type', 'date', 'etag', 'last-modified', 'content-length'}:
                    fields[key.lower()] = value.strip()
        blocks.append({'url': url, 'status': int(parts[1]), 'headers': fields})
    if not blocks or blocks[-1]['status'] != status or any(not 100 <= row['status'] < 200 for row in blocks[:-1]):
        raise ResearchSourceError('RESEARCH_SOURCE_RECEIPT_INVALID', 'origin HTTP response headers')
    return {**blocks[-1], 'informational_statuses': [row['status'] for row in blocks[:-1]]}


def fetch(url: str, destination: Path, specification: dict, curl: Path | None = None,
          *, trusted_http_connect_proxy: str) -> dict:
    config = proxy_endpoint(trusted_http_connect_proxy)
    executable = (curl or Path(shutil.which('curl') or '/missing-curl')).resolve()
    if not executable.is_file():
        raise ResearchSourceError('RESEARCH_SOURCE_FETCHER_UNAVAILABLE', 'curl')
    headers = destination.with_name('headers.tmp')
    started, responses, current = now(), [], url
    env = _curl_environment()
    try:
        for redirect_count in range(11):
            host, port, selected, addresses = _public_target(current)
            network_url, network_host, network_port = _network_url(current)
            if (host, port) != (network_host, network_port):
                raise ResearchSourceError('RESEARCH_SOURCE_ADDRESS_DRIFT', 'parsed target mismatch')
            match_host = f'[{host}]' if ':' in host else host
            connect_host = f'[{selected}]' if ':' in selected else selected
            argv = [str(executable), '-q', '--silent', '--show-error',
                    '--proxy', config['url'], '--proxytunnel', '--noproxy', '',
                    '--connect-to', f'{match_host}:{port}:{connect_host}:{port}',
                    '--suppress-connect-headers', '--proto', '=http,https',
                    '--max-time', str(specification['timeout_seconds']),
                    '--connect-timeout', str(min(20, specification['timeout_seconds'])),
                    '--max-filesize', str(specification['max_bytes_per_source']),
                    '--dump-header', str(headers), '--output', str(destination),
                    '--write-out', '%{http_code}\n%{url_effective}\n%{remote_ip}\n%{remote_port}\n%{http_connect}\n%{ssl_verify_result}',
                    '--url', network_url]
            completed = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                                       timeout=specification['timeout_seconds'] + 5, check=False, env=env)
            values = completed.stdout.splitlines()
            if (completed.returncode or len(values) != 6
                    or not all(values[i].isdigit() for i in (0, 3, 4, 5))):
                summary = f'curl_exit={completed.returncode}; connect_status={values[4] if len(values)>4 else "unknown"}; origin_status={values[0] if values else "unknown"}'
                raise ResearchSourceError('RESEARCH_SOURCE_ACQUISITION_FAILED', summary + ': ' + completed.stderr[:1000].strip())
            status, connect_status, tls_result = int(values[0]), int(values[4]), int(values[5])
            if (ipaddress.ip_address(values[2]) != ipaddress.ip_address(config['address'])
                    or int(values[3]) != config['port'] or connect_status != 200
                    or values[1] != network_url or (urlsplit(current).scheme == 'https' and tls_result != 0)):
                raise ResearchSourceError('RESEARCH_SOURCE_RECEIPT_INVALID', 'proxy peer, CONNECT, URL or TLS result mismatch')
            hop = _origin_response(headers, current, status)
            hop.update({'validated_addresses': addresses, 'selected_address': selected,
                        'connect_target': {'address': selected, 'port': port},
                        'proxy_peer': {'address': values[2], 'port': int(values[3])},
                        'connect_status': connect_status, 'effective_url': values[1],
                        'origin_socket_observed': False,
                        'origin_tls': {'required': urlsplit(current).scheme == 'https',
                                       'verification_name': host, 'verify_result': tls_result}})
            responses.append(hop)
            if status in {301, 302, 303, 307, 308} and hop['headers'].get('location'):
                if redirect_count == 10:
                    raise ResearchSourceError('RESEARCH_SOURCE_ACQUISITION_FAILED', 'redirect limit')
                current = urljoin(current, hop['headers']['location'])
                continue
            if not 200 <= status < 300 or not destination.is_file() or not destination.stat().st_size:
                raise ResearchSourceError('RESEARCH_SOURCE_ACQUISITION_FAILED', f'origin HTTP {status}')
            break
        if destination.stat().st_size > specification['max_bytes_per_source']:
            raise ResearchSourceError('RESEARCH_SOURCE_BUDGET_INSUFFICIENT', 'body bytes')
        version = subprocess.run([str(executable), '-q', '--version'], capture_output=True, text=True,
                                 encoding='utf-8', timeout=10, check=True, env=env).stdout.splitlines()[0]
        receipt = {'schema_version': TRANSPORT_SCHEMA, 'transport': config,
                   'requested_url': url, 'final_url': responses[-1]['effective_url'],
                   'http_status': status, 'redirect_count': redirect_count, 'responses': responses,
                   'public_address_policy': ADDRESS_POLICY, 'origin_socket_observed': False,
                   'media_type': responses[-1]['headers'].get('content-type', 'application/octet-stream').split(';', 1)[0].lower(),
                   'started_at': started, 'finished_at': now(),
                   'tls_verification': 'curl-default-no-insecure' if urlsplit(current).scheme == 'https' else 'none-http',
                   'fetcher': {'name': 'curl', 'path': str(executable), 'version': version, 'sha256': sha(executable)},
                   'body_sha256': sha(destination), 'body_size': destination.stat().st_size}
        _validate_receipt(receipt, url)
        return receipt
    except ResearchSourceError:
        raise
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        raise ResearchSourceError('RESEARCH_SOURCE_ACQUISITION_FAILED', str(exc)) from exc
    finally:
        headers.unlink(missing_ok=True)


def _validate_receipt(receipt: dict, source_id: str) -> None:
    """Strict offline transport checks run at seal, normal/archive verify and reuse."""
    try:
        if (receipt['schema_version'] != TRANSPORT_SCHEMA or receipt['public_address_policy'] != ADDRESS_POLICY
                or receipt['origin_socket_observed'] is not False or 'connected_address' in receipt):
            raise ValueError('transport identity')
        config = proxy_endpoint(receipt['transport']['url'])
        if config != receipt['transport']:
            raise ValueError('proxy config')
        started = datetime.fromisoformat(receipt['started_at'].replace('Z', '+00:00'))
        finished = datetime.fromisoformat(receipt['finished_at'].replace('Z', '+00:00'))
        fetcher = receipt['fetcher']
        if (started.utcoffset() != timezone.utc.utcoffset(started)
                or finished.utcoffset() != timezone.utc.utcoffset(finished) or finished < started
                or fetcher['name'] != 'curl' or not fetcher['version']
                or not re.fullmatch('[0-9a-f]{64}', fetcher['sha256'])):
            raise ValueError('time/fetcher')
        hops = receipt['responses']
        if not isinstance(hops, list) or not 1 <= len(hops) <= 11 or receipt['redirect_count'] != len(hops)-1:
            raise ValueError('hop count')
        current = receipt['requested_url']
        for index, hop in enumerate(hops):
            network_url, host, port = _network_url(current)
            addresses = [ipaddress.ip_address(a) for a in hop['validated_addresses']]
            try:
                literal = ipaddress.ip_address(host)
            except ValueError:
                literal = None
            selected = ipaddress.ip_address(hop['selected_address'])
            expected_addresses = sorted(addresses, key=lambda a: (a.version != 4, str(a)))
            if (not isinstance(hop['headers'], dict) or not isinstance(hop['informational_statuses'], list)
                    or not addresses or len(set(addresses)) != len(addresses)
                    or addresses != expected_addresses or selected != addresses[0]
                    or any(not a.is_global or a.is_multicast or a.is_reserved or a.is_unspecified for a in addresses)
                    or selected not in addresses or literal is not None and selected != literal
                    or hop['url'] != current or hop['effective_url'] != network_url
                    or hop['connect_target'] != {'address': str(selected), 'port': port}
                    or hop['proxy_peer'] != {'address': config['address'], 'port': config['port']}
                    or hop['connect_status'] != 200 or hop['origin_socket_observed'] is not False
                    or 'connected_address' in hop
                    or hop['origin_tls'] != {'required': urlsplit(current).scheme == 'https', 'verification_name': host, 'verify_result': 0}
                    or any(not isinstance(s, int) or not 100 <= s < 200 for s in hop['informational_statuses'])):
                raise ValueError('public target, peer, CONNECT or TLS')
            if index < len(hops)-1:
                if hop['status'] not in {301, 302, 303, 307, 308} or not hop['headers'].get('location'):
                    raise ValueError('redirect chain')
                current = urljoin(current, hop['headers']['location'])
            elif not 200 <= hop['status'] < 300:
                raise ValueError('origin success')
        expected_tls = 'curl-default-no-insecure' if urlsplit(current).scheme == 'https' else 'none-http'
        if (receipt['http_status'] != hops[-1]['status'] or receipt['final_url'] != hops[-1]['effective_url']
                or receipt['tls_verification'] != expected_tls or not isinstance(receipt['body_size'], int)
                or receipt['body_size'] <= 0 or not re.fullmatch('[0-9a-f]{64}', receipt['body_sha256'])):
            raise ValueError('final response/body')
    except (KeyError, TypeError, ValueError, AttributeError, ResearchSourceError) as exc:
        raise ResearchSourceError('RESEARCH_SOURCE_RECEIPT_INVALID', source_id) from exc


def _public_receipt(receipt: dict, source_id: str) -> None:
    if receipt.get('public_address_policy') == 'global-unicast-dns-pinned-no-proxy/v1':
        # Only verified v1 origins enter this compatibility path; retain original bytes.
        if receipt.get('collector_sha256') != LEGACY_COLLECTOR_SHA256:
            raise ResearchSourceError('RESEARCH_SOURCE_REUSE_INVALID', 'unknown direct collector identity')
        legacy._public_receipt(receipt, source_id)
    else:
        if receipt.get('collector_sha256') != sha(Path(__file__)):
            raise ResearchSourceError('RESEARCH_SOURCE_REUSE_INVALID', 'unknown proxy collector identity')
        _validate_receipt(receipt, source_id)


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
            trusted_http_connect_proxy: str | None = None,
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
    transport = proxy_endpoint(trusted_http_connect_proxy)
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
            receipt = (fetcher(row["url"], body, specification, curl) if fetcher else
                       fetch(row["url"], body, specification, curl, trusted_http_connect_proxy=transport["url"]))
            _validate_receipt(receipt, row["source_id"])
            if receipt["transport"] != transport:
                raise ResearchSourceError("RESEARCH_SOURCE_RECEIPT_INVALID", "fresh transport configuration")
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
                    "collector_components": _collector_components(), "transport": transport,
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
    if (document.get("collector_sha256") != sha(Path(__file__))
            or document.get("collector_components") != _collector_components()
            or document.get("transport") != proxy_endpoint(document.get("transport", {}).get("url"))):
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
            if receipt["transport"] != document["transport"]:
                raise ResearchSourceError("RESEARCH_SOURCE_RECEIPT_INVALID", "fresh transport configuration")
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
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
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
