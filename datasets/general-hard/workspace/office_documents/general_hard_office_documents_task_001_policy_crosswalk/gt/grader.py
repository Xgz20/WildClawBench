"""Private H001 rules: labelled decisions plus real, cache-free Calc results."""
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def numeric(value, expected, tolerance=0.005):
    if expected is None:
        return value is None or str(value).strip() in {"", "n.a.", "N/A", "待核实", "未覆盖", "待补正"}
    if value is None or isinstance(value, bool):
        return False
    try:
        text = str(value).strip().replace(",", "")
        actual = float(text[:-1]) / 100 if text.endswith("%") else float(text)
        return math.isfinite(actual) and abs(actual - expected) <= tolerance
    except (ValueError, TypeError):
        return False


def canonical_header(value):
    return re.sub(r"[\s_()（）]", "", str(value or "")).lower()


def table_rows(projection, contract):
    """Discover by business headers, never by sheet name, row or column order."""
    sheets = defaultdict(lambda: defaultdict(dict))
    for line in projection["text"].splitlines():
        record = json.loads(line)
        locator = record["locator"]
        if "!" not in locator:
            continue
        name, address = locator.rsplit("!", 1)
        match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", address)
        if match:
            sheets[name][int(match[2])][match[1]] = record.get("value")
    aliases = {canonical_header(alias): key for key, values in contract["field_aliases"].items() for alias in values}
    tables = []
    for sheet, rows in sheets.items():
        for number, cells in sorted(rows.items()):
            mapping = {}
            ambiguous = set()
            for column, value in cells.items():
                key = aliases.get(canonical_header(value))
                if key:
                    if key in mapping:
                        ambiguous.add(key)
                    mapping[key] = column
            for key in ambiguous:
                mapping.pop(key)
            # The source-data sheet only has case_id. A candidate decision
            # table needs an ID plus a labelled decision/evidence/action field.
            # Missing or ambiguous columns do not erase other judgeable fields.
            if "case_id" not in mapping or not set(mapping) - {"case_id"}:
                continue
            complete = not ambiguous and set(mapping) == set(contract["required_fields"])
            found = []
            for row_number, values in sorted(rows.items()):
                if row_number <= number:
                    continue
                case_id = str(values.get(mapping["case_id"]) or "").strip()
                if re.fullmatch(r"C[0-9]{2}", case_id):
                    found.append({**{key: values.get(column) for key, column in mapping.items()},
                                  "case_id": case_id, "locator": f"{sheet}!{row_number}",
                                  "_present_columns": set(mapping), "_complete_header": complete})
            if found:
                tables.append(found)
    if len(tables) != 1:
        return [], f"expected one case table, found {len(tables)}"
    return tables[0], None


def grade(root):
    root = Path(root).resolve()
    gt = root / "gt"
    expected = load(gt / "expected.json")["cases"]
    business = load(gt / "business_oracle.json")
    boundaries = load(gt / "counterexamples.json")["groups"]
    contract = load(gt / "artifact_contract.json")
    protected = load(gt / "protected_sha256.json")
    evidence = load(gt / "evidence_requirements.json")
    clause_index = load(gt / "clause_index.json")["clauses"]
    native = runpy.run_path(str(gt / "native_text.py"))
    office = runpy.run_path(str(gt / "office_runtime.py"))
    if len(expected) != 18 or set(protected) != set(evidence["protected_inputs"]):
        raise ValueError("H001 private GT contract is incomplete")
    integrity = all((root / name).is_file() and not (root / name).is_symlink()
                    and digest(root / name) == sha for name, sha in protected.items())
    output_root = Path(os.environ["GENERAL_E2E_RULE_EVIDENCE_DIR"])
    output_root.mkdir(parents=True, exist_ok=True)
    details = {"schema_version": "h001-rule-observations/v1", "protected_inputs_unchanged": integrity}
    workbook = root / contract["workbook"]
    rows, table_error, parsed = [], None, False
    if workbook.is_file() and not workbook.is_symlink():
        try:
            initial = native["extract_native_text"](workbook, max_chars=1_000_000)
            if initial["truncated"]:
                table_error = "workbook exceeds record projection limit"
            else:
                parsed = True
        except native["NativeTextError"] as exc:
            table_error = exc.code
        if parsed:
            lock = load(Path(os.environ["GENERAL_E2E_OFFICE_LOCK"]))
            recalculated = office["recalculate_xlsx"](workbook, lock, output_root / "candidate-workbook")
            projection = native["extract_native_text"](recalculated["path"], max_chars=1_000_000)
            if projection["truncated"]:
                raise RuntimeError("trusted recalculated workbook exceeds projection limit")
            rows, table_error = table_rows(projection, contract)
            details["recalculation"] = recalculated["audit"]
    else:
        table_error = "workbook missing or not a regular file"
    details["table_error"] = table_error
    table_complete = bool(rows) and all(row["_complete_header"] for row in rows)
    details["table_contract_complete"] = table_complete
    details["missing_or_ambiguous_columns"] = sorted(set(contract["required_fields"]) - rows[0]["_present_columns"]) if rows else []
    count = Counter(row["case_id"] for row in rows)
    actual = {row["case_id"]: row for row in rows if count[row["case_id"]] == 1}
    matched = {}
    binding = {}
    for label in expected:
        case_id = label["case_id"]
        row = actual.get(case_id, {})
        present = row.get("_present_columns", set())
        fields = {key: key in present and str(row.get(key) or "").strip() == label[key] for key in ("rule_set", "status")}
        fields.update({key: key in present and numeric(row.get(key), label[key], 1e-8 if key == "rate" else 0.005)
                       for key in ("rate", "cap_cny", "grant_cny")})
        # A missing row is never a correct blank/unknown case.
        if not row:
            fields = dict.fromkeys(fields, False)
        matched[case_id] = fields
        clause_text = str(row.get("clause_ids") or "")
        declared = set(re.findall(r"V[12]-(?:T[0-9]{2}|[0-9]{2})", clause_text))
        text = str(row.get("evidence") or "")
        cited = set(re.findall(r"(policies/(?:v1\.docx|v2\.pdf))#(V[12]-(?:T[0-9]{2}|[0-9]{2}))", text))
        resolved = {clause for source, clause in cited if clause in clause_index and clause_index[clause]["source"] == source
                    and clause_index[clause]["source_sha256"] == protected[source]}
        binding[case_id] = bool(declared and declared <= set(clause_index) and declared <= resolved
                                and declared.intersection(label["required_clauses"]))
    details["case_checks"] = matched
    details["evidence_bindings"] = binding
    correctness = sum(sum(weight * matched[item["case_id"]][key] for key, weight in business["field_weights"].items())
                      for item in expected) / len(expected)
    boundary_scores = {}
    for group in boundaries:
        boundary_scores[group["key"]] = sum(all(matched[case_id][key] for key in group["fields"])
                                            for case_id in group["case_ids"]) / len(group["case_ids"])
    boundary = sum(boundary_scores.values()) / len(boundary_scores)
    docx = root / contract["handoff"]
    docx_parsed = False
    if docx.is_file() and not docx.is_symlink():
        try:
            doc = native["extract_native_text"](docx, max_chars=100_000)
            docx_parsed = not doc["truncated"] and bool(doc["text"].strip())
        except native["NativeTextError"]:
            pass
    expected_ids = {item["case_id"] for item in expected}
    complete_ids = set(count) == expected_ids and all(value == 1 for value in count.values())
    actions = sum(bool(str(actual.get(case_id, {}).get("next_action") or "").strip()) for case_id in expected_ids) / len(expected_ids)
    delivery = (float(parsed and not table_error and table_complete) + float(docx_parsed) + float(complete_ids) + actions + float(integrity)) / 5
    evidence_score = sum(binding.values()) / len(expected)
    if not integrity:
        boundary, delivery, evidence_score = 0.0, 0.0, 0.0
    result = {"business_correctness": correctness, "boundary_cases": boundary,
              "delivery_integrity": delivery, "evidence_binding": evidence_score}
    result["overall_score"] = sum(result[key] * weight for key, weight in business["checkpoint_weights"].items())
    details.update(boundary_groups=boundary_scores, complete_case_ids=complete_ids, handoff_parseable=docx_parsed, scores=result)
    with (output_root / "grade-details.json").open("x", encoding="utf-8") as handle:
        json.dump(details, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return result
