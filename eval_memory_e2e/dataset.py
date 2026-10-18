"""Materialize the versioned diagnostic recipes without leaking private rubrics."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from string import Formatter

from . import DATASET_ID, DIMENSIONS, METRICS
from .io import digest, identifier, read_json, require, safe_file, sha

DATA = Path(__file__).resolve().parents[1] / "tasks" / "memory-e2e" / "memory-diagnostic20-v1.json"
OPEN_DATASET_ID = "memory-mixed20-v1"
OPEN_DATA = DATA.parent / OPEN_DATASET_ID / "manifest.json"


def load_dataset(path=DATA):
    data = read_json(path)
    require(isinstance(data, dict), "DATASET_SHAPE", "Expected a dataset object")
    if data.get("scenarios") and isinstance(data["scenarios"][0], str):
        references = data["scenarios"]
        for name in references:
            identifier(name)
        data["scenarios"] = [read_json(safe_file(Path(path).parent / name, Path(path).parent)) for name in references]
        require(all(Path(name).stem == case["id"] for name, case in zip(references, data["scenarios"])),
                "DATASET_FILENAME", "Scenario ID must match the JSON filename")
    if data.get('version') == 3:
        from .dataset_v3 import validate_v3
        return validate_v3(data, path)
    if data.get('version') == 2:
        from .dataset_v2 import validate_v2
        return validate_v2(data, path)
    require(data.get("dataset_id") in {DATASET_ID, OPEN_DATASET_ID} and type(data.get("version")) is int and data["version"] == 1,
            "DATASET_VERSION", "Unknown diagnostic dataset")
    cases = data.get("scenarios", [])
    required = {"id", "dimension", "title", "difficulty", "experience_gain", "fixtures", "steps", "checkpoints"}
    if data["dataset_id"] == OPEN_DATASET_ID:
        required.add("provenance")
    require(isinstance(cases, list) and all(isinstance(case, dict) and set(case) == required for case in cases),
            "DATASET_SHAPE", "Unknown or missing scenario fields")
    require([case["id"] for case in cases] == [f"MEM-{i:02d}" for i in range(1, 21)],
            "DATASET_SCOPE", "Expected ordered MEM-01 through MEM-20")
    require(Counter(case["dimension"] for case in cases) == DIMENSIONS,
            "DIMENSION_SCOPE", "Dimension counts must match the diagnostic contract")
    require(Counter(case["difficulty"] for case in cases) == {"easy": 6, "medium": 8, "hard": 6},
            "DIFFICULTY_SCOPE", "Expected 6/8/6 difficulty distribution")
    for case in cases:
        identifier(case["id"])
        if data["dataset_id"] == OPEN_DATASET_ID:
            provenance = case["provenance"]
            require(isinstance(provenance, dict) and provenance.get("origin") in {"open_source_adapted", "self_constructed"},
                    "SOURCE_PROVENANCE", case["id"])
            if provenance["origin"] == "open_source_adapted":
                require(all(isinstance(provenance.get(key), str) and provenance[key].strip()
                            for key in ("dataset", "original_id", "revision", "source_url", "license", "record_path", "record_sha256")),
                        "SOURCE_PROVENANCE", case["id"])
                record = safe_file(Path(path).parent / provenance["record_path"], Path(path).parent)
                require(sha(record.read_bytes()) == provenance["record_sha256"], "SOURCE_RECORD_DRIFT", case["id"])
                original = read_json(record)
                require(str(original.get("question_id", original.get("id"))) == provenance["original_id"],
                        "SOURCE_ID_MISMATCH", case["id"])
        require(type(case["experience_gain"]) is bool, "DATASET_SHAPE", "experience_gain must be bool")
        require(isinstance(case["fixtures"], list) and all(isinstance(name, str) for name in case["fixtures"])
                and len(set(case["fixtures"])) == len(case["fixtures"]), "DATASET_FIXTURE", case["id"])
        for name in case["fixtures"]:
            identifier(name)
            safe_file(Path(__file__).with_name("fixtures") / name, Path(__file__).with_name("fixtures"))
        steps, checkpoints = case["steps"], case["checkpoints"]
        require(isinstance(steps, list) and steps and isinstance(checkpoints, list) and checkpoints,
                "DATASET_SHAPE", "Steps and checkpoints must be non-empty arrays")
        require(all(isinstance(step, dict) and set(step) == {"id", "phase", "session", "scope", "prompt"} for step in steps)
                and all(isinstance(check, dict) and set(check) == {"id", "step_id", "metric", "expectation", "required"}
                        for check in checkpoints), "DATASET_SHAPE", "Unknown or missing step/checkpoint fields")
        require(any(check.get("required") is True for check in checkpoints), "NO_REQUIRED_CHECKPOINT", case["id"])
        step_ids = [step["id"] for step in steps]
        check_ids = [check["id"] for check in checkpoints]
        require(len(set(step_ids)) == len(step_ids) and len(set(check_ids)) == len(check_ids),
                "DUPLICATE_ID", case["id"])
        require(steps and checkpoints and steps[0]["session"] == "new", "DATASET_SHAPE", case["id"])
        seen_scopes = set()
        for step in steps:
            identifier(step["id"])
            require(step['id'] != 'prepare', 'RESERVED_STEP_ID', 'prepare is reserved for namespace initialization')
            require(step["phase"] in {"seed", "interference", "update", "forget", "learn", "probe"}
                    and step["session"] in {"new", "continue", "restart_new"}
                    and step["scope"] in {"A", "B"}
                    and isinstance(step["prompt"], str) and step["prompt"].strip(),
                    "DATASET_STEP", case["id"])
            require(step["session"] != "continue" or step["scope"] in seen_scopes,
                    "DATASET_SESSION", "Continuation must have a preceding session in the same scope")
            seen_scopes.add(step["scope"])
        for check in checkpoints:
            identifier(check["id"])
            require(check["step_id"] in step_ids and check["metric"] in METRICS
                    and isinstance(check["expectation"], str) and check["expectation"].strip()
                    and type(check["required"]) is bool,
                    "DATASET_CHECKPOINT", case["id"])
            target = next(step for step in steps if step["id"] == check["step_id"])
            require(target["phase"] == "probe", "DATASET_CHECKPOINT", "Only probes receive answer scores")
        require(all(step["id"] in {check["step_id"] for check in checkpoints}
                    for step in steps if step["phase"] == "probe"), "UNSCORED_PROBE", case["id"])
        for text in [step["prompt"] for step in steps] + [check["expectation"] for check in checkpoints]:
            for _, field, spec, conversion in Formatter().parse(text):
                require(field is None or (field in {"project", "code", "other", "person", "old", "new", "secret", "keep", "city", "date1", "date2"}
                        and not spec and conversion is None), "DATASET_PLACEHOLDER", str(field))
    if data["dataset_id"] == OPEN_DATASET_ID:
        composition = Counter(case["provenance"]["origin"] for case in cases)
        require(composition == {"open_source_adapted": 14, "self_constructed": 6}, "SOURCE_COMPOSITION", "Expected 14 sourced and 6 supplemental cases")
        for relative, checksum in data.get("source_assets", {}).items():
            require(sha(safe_file(Path(path).parent / relative, Path(path).parent).read_bytes()) == checksum,
                    "SOURCE_ASSET_DRIFT", relative)
    return data


def materialize(case, seed, run):
    # Same task facts across Harnesses and arms; fresh facts for each repetition.
    token = digest({"seed": seed, "scenario": case["id"], "run": run})[:20].upper()
    def field(name, length=12):
        return digest({"variant": token, "field": name})[:length].upper()
    # A query's public project name must not encode its private answer fields.
    values = {"project": f"澄屿-{field('project')}", "code": f"MC-{field('code', 16)}",
              "other": f"北辰-{field('other')}", "person": f"联系人-{field('person', 6)}",
              "old": str(1200 + int(token[:3], 16)), "new": str(7200 + int(token[3:6], 16)),
              "secret": f"PRIVATE-{field('secret', 16)}", "keep": f"KEEP-{field('keep')}",
              "city": f"星湾-{field('city', 6)}", "date1": "2026-10-20", "date2": "2026-10-23"}
    from .dataset_v2 import custom_values
    values.update(custom_values(case, token))
    result = {**case, "steps": [{**step, "prompt": step["prompt"].format_map(values)}
                               for step in case["steps"]],
              "checkpoints": [{**check, "expectation": check["expectation"].format_map(values)}
                              for check in case["checkpoints"]]}
    result["variant_id"] = token
    result["facts"] = values
    if 'gates' in case:
        result['gates'] = [{**gate, **({'expected': {key: value.format_map(values)
                            for key, value in gate['expected'].items()}} if 'expected' in gate else {})}
                           for gate in case['gates']]
    return result
