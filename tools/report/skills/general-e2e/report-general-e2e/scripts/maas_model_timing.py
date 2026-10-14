"""Report-only MaaS request timing. Never rewrite execution or score evidence."""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

PROFILE = "maas-cube-perf-v1"
CACHE_SCHEMA = "wildclawbench.maas-perf-cache/v1"
SID = re.compile(r"^cht[^\s]+@[^\s]+$")
ITEM_ID = re.compile(r"^(?:rs|resp)_(cht[^\s]+@[^\s]+)_\d+$")
ES_FIELDS = ["sid", "model", "serviceName", "result", "api_name", "request_time", "response_time", "perf", "@timestamp", "finish_reason"]
HEADERS = ["模型@Harness", "总任务耗时(s)", "总模型耗时(s)", "总模型耗时占比", "平均任务耗时(s)", "平均模型耗时(s)", "任务耗时P50(s)", "模型耗时P50(s)", "任务耗时P90(s)", "模型耗时P90(s)"]


class ModelTimingError(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise ModelTimingError(code)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False); f.write("\n"); pending = Path(f.name)
    pending.replace(path)


def numeric(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def verified_file(path, expected, sources):
    path = Path(path)
    require(not path.is_symlink(), "MODEL_TIMING_SOURCE_UNSAFE")
    require(path.is_file(), "MODEL_TIMING_SOURCE_MISSING")
    actual = digest(path)
    require(expected and actual == expected, "MODEL_TIMING_SOURCE_SHA_MISMATCH")
    sources.append({"path": str(path), "sha256": actual, "size": path.stat().st_size})
    return path


def extract_requests(row):
    result = {"unit_id": row["unit_id"], "task_id": row["task_id"], "attempt_id": row.get("execution_attempt_id"),
              "requests": [], "sources": [], "complete": False, "warnings": [], "scope": "bound-main-turn-and-compaction"}
    if row.get("harness", {}).get("id") != "astronstudio":
        result["warnings"] = ["HARNESS_MODEL_TIMING_UNSUPPORTED"]; return result
    lineage = row.get("lineage", {}); sources = result["sources"]
    record = verified_file(lineage.get("source_execution_record", ""), lineage.get("execution_record_sha256"), sources)
    ex = load(record); identity = ex["identity"]; unit = Path(lineage["source_unit_root"])
    # Standard submissions bind the immutable scoring/execution-records copy
    # beside unit/, while selected reports often use the evidence original.
    require(record.resolve().is_relative_to(unit.parent.resolve()), "MODEL_TIMING_RECORD_OUTSIDE_UNIT")
    require(identity["task_id"] == row["task_id"] and identity["attempt_id"] == row["execution_attempt_id"]
            and identity["unit_id"] == lineage.get("source_unit_id", row["unit_id"]), "MODEL_TIMING_IDENTITY_MISMATCH")
    session = ex["session"]; require(session.get("verified") is True and session.get("turn_id"), "MODEL_TIMING_SESSION_UNBOUND")
    target = session["turn_id"]; result.update(thread_id=session.get("thread_id"), turn_id=target)
    relative = row.get("tool_calls", {}).get("rollout_path")
    require(relative, "MODEL_TIMING_ROLLOUT_MISSING")
    rollout = unit.parent.parent / relative if relative.startswith("ResourceSupplements/") else unit / relative
    rollout = verified_file(rollout, row["tool_calls"].get("rollout_sha256"), sources)
    sids = {}; current = None; terminal = False; stream_errors = 0; compacted = False; meta = 0
    with rollout.open(encoding="utf-8") as f:
        for line, text in enumerate(f, 1):
            event = json.loads(text); p = event.get("payload") or {}
            if event.get("type") == "session_meta":
                meta += 1
                require(p.get("id") == session.get("session_id") and p.get("cwd") == session.get("cwd"), "MODEL_TIMING_ROLLOUT_SESSION_MISMATCH")
            if event.get("type") == "event_msg" and p.get("type") == "task_started": current = p.get("turn_id")
            if event.get("type") == "turn_context": current = p.get("turn_id")
            explicit = (p.get("internal_chat_message_metadata_passthrough") or {}).get("turn_id")
            if (explicit or current) != target: continue
            if event.get("type") == "event_msg" and p.get("type") in ["task_complete", "turn_aborted"]: terminal = True
            if event.get("type") == "event_msg" and p.get("type") in ["stream_error", "error"]: stream_errors += 1
            if event.get("type") == "compacted": compacted = True
            if event.get("type") != "response_item" or p.get("type") not in ["reasoning", "message"]: continue
            if p.get("type") == "message" and p.get("role") != "assistant": continue
            match = ITEM_ID.fullmatch(p.get("id") or "")
            if match: sids.setdefault(match[1], []).append({"path": str(rollout), "line": line, "payload_id": p["id"]})
    require(meta == 1 and terminal, "MODEL_TIMING_ROLLOUT_INCOMPLETE")
    gateway = {}; gateway_seen = False; provider = record.parent / "trace/raw/astronstudio-provider-events.jsonl"
    trace_relative = ex["evidence"].get("trace_index_path")
    trace_path = unit / trace_relative if trace_relative else None
    if trace_path:
        provider = trace_path.parent / "raw/astronstudio-provider-events.jsonl"
    trace_expected = row.get("tool_calls", {}).get("trace_index_sha256")
    refs = []
    if trace_path and trace_path.is_file() and trace_expected:
        verified_file(trace_path, trace_expected, sources); trace = load(trace_path)
        require(trace.get("identity") == identity, "MODEL_TIMING_TRACE_IDENTITY_MISMATCH")
        refs = [r for r in trace.get("raw_trace", []) if r.get("path") == "raw/astronstudio-provider-events.jsonl"]
    if provider.is_file() and len(refs) == 1:
        verified_file(provider, refs[0].get("sha256"), sources)
        with provider.open("rb") as f:
            for line, text in enumerate(f, 1):
                if b"gateway-usage.updated" not in text: continue
                event = json.loads(text)
                if event.get("event", {}).get("type") != "turn.gateway-usage.updated": continue
                if event.get("turn_id") != target or (session.get("thread_id") and event.get("thread_id") != session["thread_id"]): continue
                gateway_seen = True; payload = event.get("event", {}).get("payload", {})
                for r in payload.get("requests", []):
                    key = r.get("requestId") or r.get("responseId")
                    if not key: result["warnings"].append("GATEWAY_REQUEST_ID_MISSING"); continue
                    gateway[key] = {"request_id": r.get("requestId"), "sid": r.get("responseId"), "request_kind": r.get("requestKind"),
                                    "effective_model": r.get("effectiveModel") or r.get("requestedModel"), "native_status": r.get("status"),
                                    "provider_ref": {"path": str(provider), "line": line}}
    requests = []
    if gateway_seen and gateway:
        valid = True
        for r in gateway.values():
            if not SID.fullmatch(r.get("sid") or "") or r.get("native_status") not in ["completed", "usage_missing"]:
                valid = False; result["warnings"].append("GATEWAY_REQUEST_INCOMPLETE")
            requests.append({**r, "rollout_refs": sids.get(r.get("sid"), [])})
        seen = {r.get("sid") for r in requests}
        for sid, refs in sids.items():
            if sid not in seen:
                valid = False; requests.append({"sid": sid, "request_kind": "turn", "rollout_refs": refs})
                result["warnings"].append("ROLLOUT_SID_NOT_IN_GATEWAY_LEDGER")
        result["complete"] = valid and not result["warnings"]; result["coverage_basis"] = "native-gateway-request-ledger"
        # Some historical captures contain only the tail of gateway events.
        # A reconciled rollout can close that gap only without errors/compaction
        # or additional gateway-only requests.
        observed = row.get("resource", {}).get("request_count", {})
        if (not valid and all(r.get("sid") in sids for r in gateway.values())
                and all(w == "ROLLOUT_SID_NOT_IN_GATEWAY_LEDGER" for w in result["warnings"])
                and observed.get("complete") and observed.get("value") == len(sids)
                and not stream_errors and not compacted
                and all(r.get("native_status") in ["completed", "usage_missing"] for r in gateway.values())):
            result["complete"] = True
            result["coverage_basis"] = "partial-gateway-and-reconciled-bound-rollout"
            result["warnings"] = [w for w in result["warnings"] if w != "ROLLOUT_SID_NOT_IN_GATEWAY_LEDGER"]
    else:
        requests = [{"sid": sid, "request_kind": "turn", "rollout_refs": refs} for sid, refs in sids.items()]
        observed = row.get("resource", {}).get("request_count", {})
        result["complete"] = bool(requests) and observed.get("complete") and observed.get("value") == len(requests) and not stream_errors and not compacted and not result["warnings"]
        result["coverage_basis"] = "bound-rollout-response-and-usage-reconciliation"
        if not result["complete"]: result["warnings"].append("REQUEST_LEDGER_COVERAGE_INCOMPLETE")
    unique = {}
    for r in requests:
        if SID.fullmatch(r.get("sid") or ""):
            old = unique.get(r["sid"])
            if old and old.get("request_id") != r.get("request_id"):
                result["complete"] = False; result["warnings"].append("SID_SHARED_BY_NATIVE_REQUESTS")
            unique[r["sid"]] = r
    result["requests"] = list(unique.values()); result["expected_request_count"] = len(requests)
    if not unique: result["complete"] = False; result["warnings"].append("MODEL_REQUEST_SID_UNAVAILABLE")
    result["warnings"] = sorted(set(result["warnings"]))
    return result


def request_ledger(data):
    rows = []; owners = defaultdict(list)
    for task in data["tasks"]:
        try: row = extract_requests(task)
        except (OSError, ValueError, KeyError, TypeError) as e:
            if isinstance(e, ModelTimingError) and str(e) in ["MODEL_TIMING_SOURCE_SHA_MISMATCH", "MODEL_TIMING_IDENTITY_MISMATCH",
                    "MODEL_TIMING_RECORD_OUTSIDE_UNIT", "MODEL_TIMING_ROLLOUT_SESSION_MISMATCH", "MODEL_TIMING_TRACE_IDENTITY_MISMATCH", "MODEL_TIMING_SOURCE_UNSAFE"]:
                raise
            row = {"unit_id": task["unit_id"], "task_id": task["task_id"], "attempt_id": task.get("execution_attempt_id"),
                   "requests": [], "sources": [], "complete": False, "warnings": [str(e) if isinstance(e, ModelTimingError) else "MODEL_TIMING_SOURCE_UNAVAILABLE"]}
        rows.append(row)
        for r in row["requests"]: owners[r["sid"]].append(row)
    for sid, tasks in owners.items():
        if len({(r["unit_id"], r["task_id"], r["attempt_id"]) for r in tasks}) > 1:
            for row in tasks:
                row["complete"] = False; row["warnings"].append("SID_CROSS_TASK_OWNERSHIP_CONFLICT")
                row.setdefault("ambiguous_sids", []).append(sid)
    return {"schema_version": "wildclawbench.model-request-ledger/v1", "profile": PROFILE, "tasks": rows,
            "sids": sorted(owners), "source_count": sum(len(r["sources"]) for r in rows)}


def auth_header():
    api, bearer, user, password = [os.environ.get(k) for k in ["ES_API_KEY", "ES_BEARER_TOKEN", "ES_USERNAME", "ES_PASSWORD"]]
    require(sum(bool(x) for x in [api, bearer, user or password]) <= 1, "ES_AUTH_METHOD_CONFLICT")
    if api: return "ApiKey " + api
    if bearer: return "Bearer " + bearer
    if user or password:
        require(user and password, "ES_BASIC_AUTH_INCOMPLETE")
        return "Basic " + base64.b64encode((user + ":" + password).encode()).decode()
    return None


def fetch_cache(ledger, config, output):
    model = config.get("model", "spark-x2.5"); service = "maas_cube"; index = config.get("index", "cube-log-*")
    require(model == "spark-x2.5", "ES_MODEL_UNSUPPORTED")
    require(model and index and (config.get("es_url") or config.get("kibana_url")), "ES_ENDPOINT_UNCONFIGURED")
    require(not (config.get("es_url") and config.get("kibana_url")), "ES_ENDPOINT_AMBIGUOUS")
    context = ssl.create_default_context(cafile=config.get("ca_cert") or os.environ.get("ES_CA_CERT"))
    headers = {"Accept": "application/json", "Content-Type": "application/json"}; authorization = auth_header()
    if authorization: headers["Authorization"] = authorization
    if config.get("kibana_url"):
        parts = urlsplit(config["kibana_url"]); require(not parts.username and not parts.password, "ES_CREDENTIALS_IN_URL")
        base = parts.path.split("/app/", 1)[0].rstrip("/")
        url = urlunsplit((parts.scheme, parts.netloc, base + "/api/console/proxy", urlencode({"path": index + "/_search", "method": "POST"}), ""))
        headers["kbn-xsrf"] = "general-e2e-model-timing"
    else:
        parts = urlsplit(config["es_url"]); require(not parts.username and not parts.password, "ES_CREDENTIALS_IN_URL")
        url = config["es_url"].rstrip("/") + "/" + quote(index, safe="*,-_") + "/_search"
    require(parts.scheme in ["http", "https"] and parts.netloc, "ES_ENDPOINT_INVALID")
    page = int(config.get("page_size", 500)); batch = int(config.get("sid_batch_size", 100))
    require(1 <= page <= 1000 and 1 <= batch <= 500, "ES_QUERY_SIZE_INVALID")
    documents = {}; queries = []; sid_list = ledger["sids"]
    for start in range(0, len(sid_list), batch):
        selected = sid_list[start:start + batch]; offset = 0; total = None
        while total is None or offset < total:
            require(offset + page <= 10000, "ES_RESULT_WINDOW_EXCEEDED")
            filters = [{"term": {"model.keyword": model}},
                       {"bool": {"should": [{"term": {"serviceName.keyword": service}}, {"term": {"serviceName": service}}], "minimum_should_match": 1}},
                       {"bool": {"should": [{"terms": {"sid.keyword": selected}}, {"terms": {"sid": selected}}], "minimum_should_match": 1}}]
            payload = {"size": page, "from": offset, "track_total_hits": True, "_source": ES_FIELDS,
                       "query": {"bool": {"filter": filters}}, "sort": [{"@timestamp": "asc"}]}
            try:
                request = Request(url, json.dumps(payload).encode(), headers=headers, method="POST")
                with urlopen(request, context=context, timeout=float(config.get("timeout_seconds", 60))) as response: body = json.load(response)
            except HTTPError as e: raise ModelTimingError("ES_HTTP_ERROR_" + str(e.code)) from None
            except (URLError, TimeoutError): raise ModelTimingError("ES_NETWORK_UNAVAILABLE") from None
            require(not body.get("timed_out") and not body.get("_shards", {}).get("failed"), "ES_INCOMPLETE_QUERY")
            container = body.get("hits", {}); hits = container.get("hits"); require(isinstance(hits, list), "ES_INVALID_RESPONSE")
            declared = container.get("total"); count = declared.get("value") if isinstance(declared, dict) else declared
            require(isinstance(count, int) and (not isinstance(declared, dict) or declared.get("relation") == "eq"), "ES_HIT_COUNT_INEXACT")
            if total is None: total = count
            require(total == count, "ES_QUERY_CHANGED_DURING_PAGING")
            require(len(hits) <= page and offset + len(hits) <= total, "ES_PAGING_COUNT_MISMATCH")
            queries.append({"sid_batch": selected, "from": offset, "size": page, "total_hits": count})
            for hit in hits:
                source = hit.get("_source", {}); require(source.get("sid") in selected and source.get("model") == model and source.get("serviceName") == service, "ES_QUERY_SCOPE_MISMATCH")
                key = (hit.get("_index"), hit.get("_id")); require(all(key), "ES_DOCUMENT_ID_MISSING")
                require(key not in documents, "ES_PAGING_DUPLICATE_DOCUMENT")
                documents[key] = {"_index": key[0], "_id": key[1], "_source": {k: source[k] for k in ES_FIELDS if k in source}}
            require(hits or total == 0, "ES_PAGING_INCOMPLETE")
            offset += len(hits)
    cache = {"schema_version": CACHE_SCHEMA, "profile": PROFILE, "model": model, "service": service, "index": index,
             "fetched_at": datetime.now(timezone.utc).isoformat(), "query_complete": True, "requested_sids": sid_list,
             "queries": queries, "documents": list(documents.values())}
    save(output, cache); return cache


def normalize_cache(cache):
    require(cache.get("schema_version") == CACHE_SCHEMA and cache.get("profile") == PROFILE, "ES_CACHE_PROFILE_MISMATCH")
    require(cache.get("service") == "maas_cube" and isinstance(cache.get("query_complete"), bool), "ES_CACHE_INCOMPLETE")
    require(cache.get("model") == "spark-x2.5", "ES_MODEL_UNSUPPORTED")
    if not cache["query_complete"]:
        require(not cache["documents"], "ES_CACHE_INCOMPLETE_WITH_DOCUMENTS")
        return {}
    by_sid = defaultdict(list); model = cache["model"]
    for hit in cache["documents"]:
        r = hit.get("_source", {}); sid = r.get("sid")
        require(SID.fullmatch(sid or "") and sid in cache.get("requested_sids", [])
                and r.get("model") == model and r.get("serviceName") == "maas_cube", "ES_CACHE_SCOPE_MISMATCH")
        perf = numeric(r.get("perf")); valid = perf is not None and r.get("result") in ["success", "failed", "client_cancelled", "cancelled", "error"]
        by_sid[sid].append({"sid": sid, "perf_ms": str(perf) if perf is not None else None, "valid": valid,
                           "result": r.get("result"), "request_time": r.get("request_time"), "response_time": r.get("response_time"),
                           "index": hit.get("_index"), "id": hit.get("_id")})
    normalized = {}
    for sid, rows in by_sid.items():
        unique = {(r["perf_ms"], r["result"], r["request_time"], r["response_time"], r["valid"]) for r in rows}
        normalized[sid] = {"status": "matched" if len(unique) == 1 and rows[0]["valid"] else "ambiguous" if len(unique) > 1 else "invalid",
                           "record": rows[0], "es_refs": [{"index": r["index"], "id": r["id"]} for r in rows]}
    return normalized


def enrich(data, cache_path, *, ledger=None):
    ledger = ledger or request_ledger(data); cache = load(cache_path); records = normalize_cache(cache)
    cache_sha = digest(cache_path); task_map = {(r["unit_id"], r["task_id"]): r for r in ledger["tasks"]}
    for row in data["tasks"]:
        source = task_map[(row["unit_id"], row["task_id"])]; requests = source["requests"]
        total = Decimal(0); matched = 0; unresolved = []; refs = []; warnings = list(source["warnings"])
        if cache.get("query_error_code"): warnings.append(cache["query_error_code"])
        for request in requests:
            sid = request["sid"]; value = records.get(sid)
            if sid in source.get("ambiguous_sids", []):
                unresolved.append({"sid": sid, "reason": "SID_CROSS_TASK_OWNERSHIP_CONFLICT"}); continue
            if request.get("effective_model") and request["effective_model"] != cache["model"]:
                unresolved.append({"sid": sid, "reason": "MODEL_MISMATCH"}); continue
            if not value or value["status"] != "matched":
                unresolved.append({"sid": sid, "reason": value["status"] if value else "missing"}); continue
            total += Decimal(value["record"]["perf_ms"]) / 1000; matched += 1
            refs.append({"sid": sid, "request_kind": request.get("request_kind"), "perf_ms": value["record"]["perf_ms"], "result": value["record"]["result"], "es_refs": value["es_refs"]})
        complete = source["complete"] and not unresolved and len(requests) > 0 and matched == len(requests)
        status = "observed" if complete else "partial" if matched else "unavailable"
        native = row.get("resource", {}).get("agent_duration_seconds", {}).get("value")
        if native is not None and total > Decimal(str(native)): warnings.append("CUMULATIVE_MODEL_TIME_EXCEEDS_NATIVE_TASK_TIME")
        row["model_timing"] = {"profile": PROFILE, "status": status, "complete": complete,
            "value": float(total) if complete else None, "known_subtotal": float(total) if matched else None,
            "coverage": {"known": matched, "total": len(requests) if source["complete"] else None, "unit": "model_request"},
            "discovered_request_count": len(requests),
            "scope_complete": source["complete"], "coverage_basis": source.get("coverage_basis"), "missing_or_invalid": unresolved,
            "warnings": sorted(set(warnings)), "es_cache_sha256": cache_sha, "sources": source["sources"], "request_ledger": refs,
            "basis": "sum of unique bound SID canonical maas_cube.perf / 1000; includes terminal failed/cancelled and compaction requests; not pure inference or wall-time union"}
    data["model_timing_provenance"] = {"profile": PROFILE, "es_cache_sha256": cache_sha, "es_model": cache["model"], "service": "maas_cube", "metric": "perf", "unit": "ms",
                                       "query_complete": cache["query_complete"], "query_error_code": cache.get("query_error_code"),
                                       "query_requested_sid_count": len(cache.get("requested_sids", [])), "es_document_count": len(cache["documents"])}
    return ledger


def summarize(rows):
    observations = [r.get("model_timing", {}) for r in rows]; values = [numeric(o.get("value")) for o in observations if o.get("complete")]
    known = [numeric(o.get("known_subtotal")) for o in observations]; known = [v for v in known if v is not None]
    complete = bool(rows) and len(values) == len(rows) and all(v is not None for v in values)
    return {"total": float(sum(values, Decimal(0))) if complete else None, "known_subtotal": float(sum(known, Decimal(0))) if known else None,
            "complete": complete, "known_cases": len(values), "total_cases": len(rows), "values": [float(v) for v in values if v is not None],
            "matched_requests": sum(o.get("coverage", {}).get("known", 0) for o in observations),
            "expected_requests": sum(o.get("coverage", {}).get("total") or 0 for o in observations),
            "unknown_request_denominator_cases": sum(o.get("coverage", {}).get("total") is None for o in observations)}


def attach_views(data):
    import report_views
    labels = data["presentation"]["unit_labels"]; efficiency = data["presentation"]["tables"]["效率对比"]
    report_views.attach_task_timing(data, efficiency, labels)
    for extra in efficiency.get("additional_views", []):
        ids = data.get("resource_exclusion_analysis", {}).get("included_task_ids")
        require(ids is not None, "MODEL_TIMING_ADDITIONAL_SCOPE_UNSPECIFIED")
        filtered = {**data, "tasks": [r for r in data["tasks"] if r["task_id"] in set(ids)], "units": []}
        import report_general_e2e
        for unit in data["units"]:
            included = [r for r in filtered["tasks"] if r["unit_id"] == unit["unit_id"]]
            filtered["units"].append({**unit, "resources": report_general_e2e.resource_summary(included)})
        # Keep sections below the expanded main coverage/notes region.
        extra["header_row"] = max(extra.get("header_row", 2), efficiency["render_row_count"] + 4)
        old_notes = extra.get("timing_table", {}).get("notes", []); old_title = extra.get("timing_table", {}).get("title")
        timing = report_views.attach_task_timing(filtered, extra, labels)
        if old_title: timing["title"] = old_title
        if old_notes:
            extra_notes = [n for n in old_notes if "统一剔除" in n or "58" in n]
            timing["notes"] = list(dict.fromkeys(timing["notes"] + extra_notes))
            timing["coverage_title_row"] = timing["header_row"] + len(timing["rows"]) + len(timing["notes"]) + 5
            timing["render_end_row"] = timing["coverage_title_row"] + 1 + len(timing["coverage_table"]["rows"])
            extra["render_row_count"] = timing["render_end_row"]
        efficiency["render_row_count"] = max(efficiency["render_row_count"], extra["render_row_count"])


def add_arguments(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--maas-es-cache", type=Path, help="报告阶段读取已冻结的maas_cube.perf最小字段缓存")
    group.add_argument("--maas-es-config", type=Path, help="报告阶段按SID补采ES；认证只从ES_*环境变量读取")


def apply_options(data, args, output_dir):
    cache = getattr(args, "maas_es_cache", None); config = getattr(args, "maas_es_config", None)
    if not cache and not config: return []
    output = Path(output_dir) / "model-timing"; output.mkdir(parents=True, exist_ok=True)
    ledger = request_ledger(data); save(output / "request-ledger.json", ledger)
    target = output / "es-cache.json"
    if config:
        try:
            fetch_cache(ledger, load(config), target)
        except ModelTimingError as error:
            save(target, {"schema_version": CACHE_SCHEMA, "profile": PROFILE, "model": "spark-x2.5", "service": "maas_cube",
                          "query_complete": False, "query_error_code": str(error), "requested_sids": ledger["sids"], "documents": []})
    else: save(target, load(cache))
    enrich(data, target, ledger=ledger)
    if "presentation" in data: attach_views(data)
    save(output / "coverage.json", {"profile": PROFILE, "units": {u["unit_id"]: summarize([r for r in data["tasks"] if r["unit_id"] == u["unit_id"]]) for u in data["units"]}})
    return [output / "request-ledger.json", target, output / "coverage.json"]


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch"); fetch.add_argument("--report-json", type=Path, required=True); fetch.add_argument("--config", type=Path, required=True); fetch.add_argument("--output-cache", type=Path, required=True)
    edit = sub.add_parser("enrich"); edit.add_argument("--input-json", type=Path, required=True); edit.add_argument("--output-json", type=Path, required=True); edit.add_argument("--es-cache", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "fetch":
            data = load(args.report_json); ledger = request_ledger(data); cache = fetch_cache(ledger, load(args.config), args.output_cache)
            save(args.output_cache.with_suffix(".requests.json"), ledger)
            print(json.dumps({"status": "PASS", "sid_count": len(ledger["sids"]), "documents": len(cache["documents"]), "cache": str(args.output_cache)}))
        else:
            require(args.input_json.resolve() != args.output_json.resolve() and not args.output_json.exists(), "MODEL_TIMING_OUTPUT_NOT_NEW")
            data = load(args.input_json); enrich(data, args.es_cache); attach_views(data); save(args.output_json, data)
            print(json.dumps({"status": "PASS", "output": str(args.output_json)}))
    except (ModelTimingError, OSError, ValueError) as e:
        print(json.dumps({"status": "FAIL", "error": str(e) if isinstance(e, ModelTimingError) else "MODEL_TIMING_OPERATION_FAILED"})); return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
