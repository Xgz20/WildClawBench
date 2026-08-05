#!/usr/bin/env python3
"""Static validation for the WildClawBench extension task set.

The validator joins four authoring artifacts that must stay consistent:

* ``tasks/extension/**/*.md`` task definitions;
* ``tasks/extension/task_sources.yaml`` source and reserved-number records;
* ``workspace/extension/**`` task inputs and ground truth; and
* ``tools/report/data/checkpoint_capability_map7.yaml`` capability mappings.

It performs no network access and does not execute task grading code.
"""

from __future__ import annotations

import argparse
import ast
import ipaddress
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlsplit

import yaml


CATEGORIES = (
    "01_Productivity_Flow",
    "02_Code_Intelligence",
    "03_Social_Interaction",
    "04_Search_Retrieval",
    "05_Creative_Synthesis",
    "06_Safety_Alignment",
)
DIFFICULTIES = {"L1", "L2", "L3", "L4"}
GRADING_TYPES = {"automated", "llm_judge", "hybrid"}
CAPABILITIES = {
    "code_generation",
    "tool_use",
    "data_processing",
    "retrieval_verification",
    "reasoning_planning",
    "content_generation",
    "verification_delivery",
}
RUNTIME_SOURCE_REGIONS = {
    "mainland_china_official",
    "overseas_official",
    "international_authoritative_third_party",
}
ALLOWED_HYBRID_WEIGHTS = {(0.7, 0.3), (0.4, 0.6)}
ALLOWED_ATTACHMENT_LIMITS_MB = {5, 20}
MIB = 1024 * 1024

TASK_ID_RE = re.compile(
    r"^(?P<category>0[1-6]_[A-Za-z][A-Za-z0-9_]*)_task_"
    r"(?P<number>(?!000)[0-9]{3})_(?P<slug>[a-z0-9]+(?:_[a-z0-9]+)*)$"
)
SHORT_ID_RE = re.compile(r"^(?P<category>0[1-6])-(?P<number>(?!000)[0-9]{3})$")
CRITERION_HEADING_RE = re.compile(
    r"^###\s+.*?\(key:\s*([A-Za-z0-9_-]+)\s*,\s*weight:\s*([0-9.]+)\s*\)\s*$"
)
SCORE_BAND_RE = re.compile(
    r"\*\*Score\s+(1(?:\.0)?|0\.75|0\.5|0\.25|0(?:\.0)?)\*\*\s*:"
)
TMP_WORKSPACE_PATH_RE = re.compile(
    r"/tmp_workspace(?:/[^/\s`<>()\[\]{}\"'，。；：,;:]+)*/?"
)
HTTP_URL_RE = re.compile(r"https?://[^\s`<>()\[\]{}\"']+")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


@dataclass(frozen=True, order=True)
class ValidationIssue:
    code: str
    location: str
    message: str

    def format(self) -> str:
        return f"[{self.code}] {self.location}: {self.message}"


@dataclass
class ParsedTask:
    path: Path
    metadata: dict[str, Any]
    sections: dict[str, str]
    task_id: str
    category: str
    number: int
    slug: str
    workspace_dir: Path | None = None
    automated_keys: set[str] | None = None
    rubric_keys: set[str] | None = None


def _load_yaml(path: Path) -> Any:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=0.0, abs_tol=1e-9)


def _is_https_url(value: Any) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or any(char.isspace() for char in value)
        or "\\" in value
        or re.search(r"%(?![0-9A-Fa-f]{2})", value)
    ):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        return False
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        return False
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
        port = parsed.port
    except (UnicodeError, ValueError):
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    try:
        ipaddress.ip_address(ascii_hostname)
    except ValueError:
        if len(ascii_hostname) > 253 or re.fullmatch(r"[0-9.]+", ascii_hostname):
            return False
        labels = ascii_hostname.split(".")
        if len(labels) < 2 or any(
            not label
            or len(label) > 63
            or re.fullmatch(r"[A-Za-z0-9-]+", label) is None
            or label.startswith("-")
            or label.endswith("-")
            for label in labels
        ):
            return False
    return True


def _parse_markdown(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError("YAML frontmatter not found")
    metadata = yaml.load(match.group(1), Loader=UniqueKeyLoader)
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a YAML mapping")

    sections: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in match.group(2).splitlines():
        heading = re.match(r"^##\s+(.+?)\s*$", line)
        if heading:
            if current is not None:
                sections[current] = "\n".join(body).strip()
            current = heading.group(1)
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        sections[current] = "\n".join(body).strip()
    return metadata, sections


def _first_fenced_block(value: str) -> str:
    match = re.search(r"```[^\n]*\n(.*?)\n```", value, re.DOTALL)
    return match.group(1).strip() if match else value.strip()


def _literal_string_collection(
    node: ast.AST, collections: dict[str, set[str]]
) -> set[str] | None:
    if isinstance(node, ast.Name):
        return collections.get(node.id)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: set[str] = set()
        for item in node.elts:
            if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
                return None
            values.add(item.value)
        return values
    return None


def _dict_string_keys(node: ast.AST) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    return {
        key.value
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def _subscript_string_key(node: ast.Subscript) -> str | None:
    index = node.slice
    if isinstance(index, ast.Constant) and isinstance(index.value, str):
        return index.value
    return None


def _extract_automated_keys(code: str) -> tuple[set[str], str | None]:
    """Extract score dictionary keys without executing author-provided code."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return set(), f"Automated Checks is not valid Python: {exc.msg} (line {exc.lineno})"

    grade_functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "grade"
    ]
    if not grade_functions:
        return set(), "Automated Checks must define grade()"
    grade = grade_functions[0]

    returned_names = {
        node.value.id
        for node in ast.walk(grade)
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name)
    }
    score_names = {"scores"} | returned_names
    collections: dict[str, set[str]] = {}

    # Resolve simple literal lists used by patterns such as
    # ``scores = {key: 0.0 for key in keys}``.
    for node in ast.walk(grade):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                values = _literal_string_collection(node.value, collections)
                if values is not None:
                    collections[target.id] = values

    keys: set[str] = set()
    for node in ast.walk(grade):
        if isinstance(node, ast.Return) and node.value is not None:
            keys.update(_dict_string_keys(node.value))

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[ast.AST]
            value: ast.AST | None
            if isinstance(node, ast.Assign):
                targets, value = list(node.targets), node.value
            else:
                targets, value = [node.target], node.value
            for target in targets:
                if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
                    if target.value.id in score_names:
                        key = _subscript_string_key(target)
                        if key is not None:
                            keys.add(key)
                if (
                    not isinstance(target, ast.Name)
                    or target.id not in score_names
                    or value is None
                ):
                    continue
                keys.update(_dict_string_keys(value))
                if isinstance(value, ast.DictComp):
                    for generator in value.generators:
                        values = _literal_string_collection(generator.iter, collections)
                        if values is not None:
                            keys.update(values)
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Attribute)
                    and isinstance(value.func.value, ast.Name)
                    and value.func.value.id == "dict"
                    and value.func.attr == "fromkeys"
                    and value.args
                ):
                    values = _literal_string_collection(value.args[0], collections)
                    if values is not None:
                        keys.update(values)

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in score_names
            and node.func.attr == "update"
            and node.args
        ):
            keys.update(_dict_string_keys(node.args[0]))

    return keys, None


def _parse_rubric(section: str) -> tuple[list[tuple[str, float, str]], list[str]]:
    criteria: list[tuple[str, float, str]] = []
    errors: list[str] = []
    current_key: str | None = None
    current_weight = 0.0
    body: list[str] = []

    def finish() -> None:
        nonlocal current_key, current_weight, body
        if current_key is not None:
            criteria.append((current_key, current_weight, "\n".join(body)))

    for line in section.splitlines():
        if line.startswith("###"):
            match = CRITERION_HEADING_RE.match(line.strip())
            if match:
                finish()
                current_key = match.group(1)
                try:
                    current_weight = float(match.group(2))
                except ValueError:
                    current_weight = math.nan
                body = []
            elif re.match(r"^###\s+Criterion\b", line, re.IGNORECASE):
                errors.append(f"invalid criterion heading: {line.strip()}")
        elif current_key is not None:
            body.append(line)
    finish()
    return criteria, errors


class ExtensionTaskValidator:
    def __init__(self, repo_root: Path, *, allow_incomplete: bool = False):
        self.repo_root = repo_root.resolve()
        self.allow_incomplete = allow_incomplete
        self.tasks_root = self.repo_root / "tasks" / "extension"
        self.workspace_root = self.repo_root / "workspace" / "extension"
        self.sources_path = self.tasks_root / "task_sources.yaml"
        self.capability_map_path = (
            self.repo_root / "tools" / "report" / "data" / "checkpoint_capability_map7.yaml"
        )
        self.issues: list[ValidationIssue] = []
        self.task_records: dict[str, dict[str, Any]] = {}
        self.excluded_records: dict[str, dict[str, Any]] = {}
        self.capability_map: dict[str, Any] = {}
        self.loaded_task_count = 0

    def add(self, code: str, location: str | Path, message: str) -> None:
        try:
            display = str(Path(location).resolve().relative_to(self.repo_root))
        except (TypeError, ValueError):
            display = str(location)
        self.issues.append(ValidationIssue(code, display, message))

    def validate(self) -> list[ValidationIssue]:
        self._load_sources()
        self._load_capability_map()
        tasks = self._load_tasks()
        self.loaded_task_count = len(tasks)
        self._validate_source_coverage(tasks)
        for task in tasks.values():
            self._validate_task(task)
        self._validate_mapping_orphans(tasks)
        return sorted(set(self.issues))

    def _load_sources(self) -> None:
        if not self.sources_path.is_file():
            self.add("sources.missing", self.sources_path, "source registry is missing")
            return
        try:
            document = _load_yaml(self.sources_path)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            self.add("sources.yaml", self.sources_path, f"cannot parse YAML: {exc}")
            return
        if not isinstance(document, dict):
            self.add("sources.shape", self.sources_path, "top level must be a mapping")
            return
        tasks = document.get("tasks")
        excluded = document.get("excluded_tasks")
        if not isinstance(tasks, list):
            self.add("sources.tasks", self.sources_path, "tasks must be a list")
            tasks = []
        if not isinstance(excluded, list):
            self.add("sources.excluded", self.sources_path, "excluded_tasks must be a list")
            excluded = []
        self._validate_registry_contract(document.get("registry_contract"), tasks, excluded)

        allocations: dict[tuple[str, int], str] = {}
        short_ids: dict[str, str] = {}
        for index, raw_record in enumerate(tasks):
            record = self._validate_source_record(raw_record, f"tasks[{index}]", excluded=False)
            if record is not None:
                self._register_source_record(
                    record, self.task_records, allocations, short_ids, f"tasks[{index}]"
                )
        for index, raw_record in enumerate(excluded):
            record = self._validate_source_record(
                raw_record, f"excluded_tasks[{index}]", excluded=True
            )
            if record is not None:
                self._register_source_record(
                    record,
                    self.excluded_records,
                    allocations,
                    short_ids,
                    f"excluded_tasks[{index}]",
                )

        by_category: dict[str, set[int]] = {}
        for category, number in allocations:
            by_category.setdefault(category, set()).add(number)
        for category, numbers in by_category.items():
            missing = sorted(set(range(1, max(numbers) + 1)) - numbers)
            if missing:
                formatted = ", ".join(f"{number:03d}" for number in missing)
                self.add(
                    "numbering.gap",
                    self.sources_path,
                    f"{category} has unreserved number(s): {formatted}",
                )

    def _validate_registry_contract(
        self, raw_contract: Any, tasks: list[Any], excluded: list[Any]
    ) -> None:
        """Validate the registry-level task-count and invalid-number lock."""
        if not isinstance(raw_contract, dict):
            self.add(
                "sources.contract",
                self.sources_path,
                "registry_contract must be a mapping",
            )
            return

        expected_active = raw_contract.get("active_task_count")
        if (
            isinstance(expected_active, bool)
            or not isinstance(expected_active, int)
            or expected_active < 0
        ):
            self.add(
                "sources.contract",
                self.sources_path,
                "registry_contract.active_task_count must be a non-negative integer",
            )
        elif len(tasks) != expected_active:
            self.add(
                "sources.contract_count",
                self.sources_path,
                f"registry has {len(tasks)} active task record(s); expected {expected_active}",
            )

        expected_by_category = raw_contract.get("category_task_counts")
        if not isinstance(expected_by_category, dict):
            self.add(
                "sources.contract",
                self.sources_path,
                "registry_contract.category_task_counts must be a mapping",
            )
        else:
            actual_by_category: dict[str, int] = {}
            for record in tasks:
                if not isinstance(record, dict) or not isinstance(
                    record.get("task_id"), str
                ):
                    continue
                match = TASK_ID_RE.fullmatch(record["task_id"])
                if match:
                    category = match.group("category")
                    actual_by_category[category] = actual_by_category.get(category, 0) + 1
            invalid_fields = False
            for category, count in expected_by_category.items():
                if (
                    category not in CATEGORIES
                    or isinstance(count, bool)
                    or not isinstance(count, int)
                    or count < 0
                ):
                    invalid_fields = True
                    continue
                actual_count = actual_by_category.get(category, 0)
                if actual_count != count:
                    self.add(
                        "sources.contract_category",
                        self.sources_path,
                        f"{category} has {actual_count} active task record(s); "
                        f"expected {count}",
                    )
            uncontracted = set(actual_by_category) - set(expected_by_category)
            if uncontracted:
                self.add(
                    "sources.contract_category",
                    self.sources_path,
                    f"active task categories absent from registry_contract: "
                    f"{sorted(uncontracted)}",
                )
            valid_counts = [
                count
                for category, count in expected_by_category.items()
                if category in CATEGORIES
                and isinstance(count, int)
                and not isinstance(count, bool)
                and count >= 0
            ]
            if (
                isinstance(expected_active, int)
                and not isinstance(expected_active, bool)
                and expected_active >= 0
                and sum(valid_counts) != expected_active
            ):
                self.add(
                    "sources.contract",
                    self.sources_path,
                    "category_task_counts must sum to active_task_count",
                )
            if invalid_fields:
                self.add(
                    "sources.contract",
                    self.sources_path,
                    "category_task_counts must use supported categories and "
                    "non-negative integer counts",
                )

        expected_invalid = raw_contract.get("reserved_invalid_short_ids")
        if (
            not isinstance(expected_invalid, list)
            or any(not isinstance(value, str) for value in expected_invalid)
            or len(expected_invalid) != len(set(expected_invalid))
        ):
            self.add(
                "sources.contract",
                self.sources_path,
                "registry_contract.reserved_invalid_short_ids must be a unique string list",
            )
        else:
            actual_invalid = {
                record.get("short_id")
                for record in excluded
                if isinstance(record, dict) and isinstance(record.get("short_id"), str)
            }
            if actual_invalid != set(expected_invalid):
                self.add(
                    "sources.contract_invalid",
                    self.sources_path,
                    f"reserved invalid short IDs are {sorted(actual_invalid)}; "
                    f"expected {sorted(expected_invalid)}",
                )

    def _validate_source_record(
        self, raw_record: Any, location: str, *, excluded: bool
    ) -> dict[str, Any] | None:
        full_location = f"{self.sources_path}:{location}"
        if not isinstance(raw_record, dict):
            self.add("sources.record", full_location, "record must be a mapping")
            return None
        task_id = raw_record.get("task_id")
        short_id = raw_record.get("short_id")
        task_match = TASK_ID_RE.fullmatch(task_id) if isinstance(task_id, str) else None
        short_match = SHORT_ID_RE.fullmatch(short_id) if isinstance(short_id, str) else None
        if not task_match:
            self.add("id.format", full_location, f"invalid task_id: {task_id!r}")
            return None
        category = task_match.group("category")
        if category not in CATEGORIES:
            self.add("id.category", full_location, f"unsupported category: {category}")
        if not short_match:
            self.add("short_id.format", full_location, f"invalid short_id: {short_id!r}")
        else:
            expected_short = f"{task_match.group('category')[:2]}-{task_match.group('number')}"
            if short_id != expected_short:
                self.add(
                    "short_id.mismatch",
                    full_location,
                    f"expected {expected_short!r} for {task_id}",
                )

        if excluded:
            if raw_record.get("status") != "invalid":
                self.add("invalid.status", full_location, "excluded task status must be invalid")
            if raw_record.get("number_reserved") is not True:
                self.add(
                    "invalid.reservation", full_location, "excluded task must reserve its number"
                )
        else:
            design_origin = raw_record.get("design_origin")
            if not isinstance(design_origin, dict):
                self.add(
                    "sources.design_origin", full_location, "design_origin must be a mapping"
                )
            else:
                references = design_origin.get("references")
                if not isinstance(references, list):
                    self.add(
                        "sources.references",
                        full_location,
                        "design_origin.references must be a list",
                    )
                else:
                    for ref_index, reference in enumerate(references):
                        ref_location = f"{full_location}.design_origin.references[{ref_index}]"
                        if not isinstance(reference, dict) or not _is_https_url(
                            reference.get("url")
                        ):
                            self.add(
                                "url.invalid",
                                ref_location,
                                "reference url must be an absolute HTTPS URL without credentials",
                            )

            runtime_sources = raw_record.get("runtime_sources")
            if not isinstance(runtime_sources, list):
                self.add(
                    "sources.runtime_sources", full_location, "runtime_sources must be a list"
                )
            else:
                seen_urls: set[str] = set()
                for source_index, source in enumerate(runtime_sources):
                    source_location = f"{full_location}.runtime_sources[{source_index}]"
                    if not isinstance(source, dict):
                        self.add(
                            "sources.runtime_source", source_location, "entry must be a mapping"
                        )
                        continue
                    url = source.get("url")
                    if not _is_https_url(url):
                        self.add(
                            "url.invalid",
                            source_location,
                            "runtime source url must be an absolute HTTPS URL without credentials",
                        )
                    elif url in seen_urls:
                        self.add(
                            "url.duplicate", source_location, f"duplicate runtime URL: {url}"
                        )
                    else:
                        seen_urls.add(url)
                    if source.get("region") not in RUNTIME_SOURCE_REGIONS:
                        self.add(
                            "sources.region",
                            source_location,
                            f"region must be one of {sorted(RUNTIME_SOURCE_REGIONS)}",
                        )
                    for field in ("organization", "stable_id", "verification_status"):
                        if not isinstance(source.get(field), str) or not source[field].strip():
                            self.add(
                                "sources.runtime_field",
                                source_location,
                                f"{field} must be a non-empty string",
                            )
        return raw_record

    def _register_source_record(
        self,
        record: dict[str, Any],
        target: dict[str, dict[str, Any]],
        allocations: dict[tuple[str, int], str],
        short_ids: dict[str, str],
        location: str,
    ) -> None:
        task_id = record["task_id"]
        match = TASK_ID_RE.fullmatch(task_id)
        assert match is not None
        allocation = (match.group("category"), int(match.group("number")))
        if task_id in self.task_records or task_id in self.excluded_records:
            self.add("id.duplicate", self.sources_path, f"duplicate task_id: {task_id}")
        else:
            target[task_id] = record
        previous = allocations.get(allocation)
        if previous is not None and previous != task_id:
            self.add(
                "numbering.reused",
                self.sources_path,
                f"{allocation[0]} number {allocation[1]:03d} is used by {previous} and {task_id}",
            )
        else:
            allocations[allocation] = task_id
        short_id = record.get("short_id")
        if isinstance(short_id, str):
            previous_short = short_ids.get(short_id)
            if previous_short is not None and previous_short != task_id:
                self.add(
                    "short_id.duplicate",
                    self.sources_path,
                    f"{short_id} is used by {previous_short} and {task_id}",
                )
            else:
                short_ids[short_id] = task_id

    def _load_capability_map(self) -> None:
        if not self.capability_map_path.is_file():
            self.add(
                "capability_map.missing", self.capability_map_path, "capability map is missing"
            )
            return
        try:
            document = _load_yaml(self.capability_map_path)
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            self.add(
                "capability_map.yaml", self.capability_map_path, f"cannot parse YAML: {exc}"
            )
            return
        if not isinstance(document, dict):
            self.add(
                "capability_map.shape", self.capability_map_path, "top level must be a mapping"
            )
            return
        self.capability_map = document

    def _load_tasks(self) -> dict[str, ParsedTask]:
        tasks: dict[str, ParsedTask] = {}
        allocations: dict[tuple[str, int], str] = {}
        if not self.tasks_root.is_dir():
            self.add("tasks.missing", self.tasks_root, "extension task directory is missing")
            return tasks
        for path in sorted(self.tasks_root.glob("*/*.md")):
            try:
                metadata, sections = _parse_markdown(path)
            except (OSError, UnicodeError, ValueError, yaml.YAMLError) as exc:
                self.add("task.parse", path, str(exc))
                continue
            raw_task_id = metadata.get("id")
            match = TASK_ID_RE.fullmatch(raw_task_id) if isinstance(raw_task_id, str) else None
            if not match:
                self.add("id.format", path, f"invalid frontmatter id: {raw_task_id!r}")
                continue
            task = ParsedTask(
                path=path,
                metadata=metadata,
                sections=sections,
                task_id=raw_task_id,
                category=match.group("category"),
                number=int(match.group("number")),
                slug=match.group("slug"),
            )
            allocation = (task.category, task.number)
            previous = allocations.get(allocation)
            if previous is not None and previous != task.task_id:
                self.add(
                    "numbering.reused",
                    path,
                    f"number {task.number:03d} is also used by {previous}",
                )
            else:
                allocations[allocation] = task.task_id
            if raw_task_id in tasks:
                self.add("id.duplicate", path, f"duplicate task id: {raw_task_id}")
            else:
                tasks[raw_task_id] = task
        return tasks

    def _validate_source_coverage(self, tasks: dict[str, ParsedTask]) -> None:
        registered = set(self.task_records) | set(self.excluded_records)
        for task_id, task in tasks.items():
            if task_id not in registered:
                self.add(
                    "sources.unregistered", task.path, "task is absent from task_sources.yaml"
                )
        if self.allow_incomplete:
            return
        for task_id in sorted(registered - set(tasks)):
            self.add(
                "task.missing",
                self.sources_path,
                f"registered task has no Markdown file: {task_id}",
            )

    def _validate_task(self, task: ParsedTask) -> None:
        metadata = task.metadata
        if task.path.stem != task.task_id:
            self.add(
                "id.filename",
                task.path,
                f"filename stem {task.path.stem!r} must equal id {task.task_id!r}",
            )
        if task.path.parent.name != task.category:
            self.add(
                "id.directory",
                task.path,
                f"task id category {task.category!r} must equal parent directory",
            )
        if task.category not in CATEGORIES:
            self.add("id.category", task.path, f"unsupported category: {task.category}")
        if metadata.get("category") != task.category:
            self.add(
                "category.mismatch",
                task.path,
                f"frontmatter category must be {task.category!r}",
            )
        difficulty = metadata.get("difficulty")
        if difficulty not in DIFFICULTIES:
            self.add(
                "difficulty.invalid", task.path, f"difficulty must be one of {sorted(DIFFICULTIES)}"
            )
        grading_type = metadata.get("grading_type")
        if grading_type not in GRADING_TYPES:
            self.add(
                "grading_type.invalid",
                task.path,
                f"grading_type must be one of {sorted(GRADING_TYPES)}",
            )
        tags = metadata.get("tags")
        normalized_tags = (
            {str(tag).strip().lower() for tag in tags}
            if isinstance(tags, list)
            else {part.strip().lower() for part in tags.split(",")}
            if isinstance(tags, str)
            else set()
        )
        if task.task_id in self.excluded_records:
            if "invalid" not in normalized_tags:
                self.add("invalid.tag", task.path, "reserved invalid task must have tag invalid")
        else:
            if "custom" not in normalized_tags:
                self.add("tags.custom", task.path, "active extension task must have tag custom")
            if "invalid" in normalized_tags:
                self.add(
                    "invalid.registry",
                    task.path,
                    "task tagged invalid must be listed under excluded_tasks",
                )

        self._validate_grading(task, grading_type)
        self._validate_workspace(task)
        self._validate_prompt_paths_and_urls(task)
        self._validate_capabilities(task, grading_type)

    def _validate_grading(self, task: ParsedTask, grading_type: Any) -> None:
        weights = task.metadata.get("grading_weights")
        if isinstance(weights, dict):
            unknown = set(weights) - {"automated", "llm_judge"}
            if unknown:
                self.add(
                    "weights.fields",
                    task.path,
                    f"unexpected grading_weights fields: {sorted(unknown)}",
                )
        if grading_type == "hybrid":
            if not isinstance(weights, dict):
                self.add(
                    "weights.missing", task.path, "hybrid task requires grading_weights mapping"
                )
            else:
                automated = _numeric(weights.get("automated"))
                judge = _numeric(weights.get("llm_judge"))
                if automated is None or judge is None:
                    self.add(
                        "weights.invalid",
                        task.path,
                        "automated and llm_judge weights must be finite numbers",
                    )
                elif not _close(automated + judge, 1.0):
                    self.add("weights.sum", task.path, "grading_weights must sum to 1")
                elif not any(
                    _close(automated, expected_auto) and _close(judge, expected_judge)
                    for expected_auto, expected_judge in ALLOWED_HYBRID_WEIGHTS
                ):
                    self.add(
                        "weights.mode",
                        task.path,
                        "extension hybrid weights must be 0.7/0.3 or 0.4/0.6",
                    )
        elif grading_type in {"automated", "llm_judge"} and weights is not None:
            if not isinstance(weights, dict):
                self.add("weights.invalid", task.path, "grading_weights must be a mapping")
            else:
                automated = _numeric(weights.get("automated", 0.0))
                judge = _numeric(weights.get("llm_judge", 0.0))
                expected = (1.0, 0.0) if grading_type == "automated" else (0.0, 1.0)
                if automated is None or judge is None or not (
                    _close(automated, expected[0]) and _close(judge, expected[1])
                ):
                    self.add(
                        "weights.mode",
                        task.path,
                        f"{grading_type} grading_weights must be {expected[0]:g}/{expected[1]:g}",
                    )

        auto_section = task.sections.get("Automated Checks", "")
        if grading_type in {"automated", "hybrid"}:
            code = _first_fenced_block(auto_section)
            if not code:
                self.add(
                    "automated.missing", task.path, "task requires an Automated Checks grade()"
                )
                task.automated_keys = set()
            else:
                keys, error = _extract_automated_keys(code)
                if error:
                    self.add("automated.invalid", task.path, error)
                task.automated_keys = keys - {"overall_score"}
                if not task.automated_keys:
                    self.add(
                        "automated.checkpoints",
                        task.path,
                        "no automated checkpoint keys could be determined statically",
                    )
        else:
            task.automated_keys = set()

        rubric_section = task.sections.get("LLM Judge Rubric", "")
        criteria, rubric_errors = _parse_rubric(rubric_section)
        for error in rubric_errors:
            self.add("rubric.heading", task.path, error)
        task.rubric_keys = {key for key, _, _ in criteria}
        if grading_type in {"hybrid", "llm_judge"}:
            if not criteria:
                self.add(
                    "rubric.missing", task.path, "task requires at least one Judge criterion"
                )
            keys = [key for key, _, _ in criteria]
            if len(keys) != len(set(keys)):
                self.add("rubric.keys", task.path, "Judge criterion keys must be unique")
            rubric_weights = [weight for _, weight, _ in criteria]
            if any(not math.isfinite(weight) or weight <= 0 for weight in rubric_weights):
                self.add("rubric.weights", task.path, "criterion weights must be positive numbers")
            elif criteria and not _close(sum(rubric_weights), 1.0):
                self.add("rubric.weights", task.path, "criterion weights must sum to 1")
            required_bands = {0.0, 0.25, 0.5, 0.75, 1.0}
            for key, _, body in criteria:
                bands = {float(value) for value in SCORE_BAND_RE.findall(body)}
                if bands != required_bands:
                    self.add(
                        "rubric.bands",
                        task.path,
                        f"criterion {key!r} must declare exactly 1/0.75/0.5/0.25/0 bands",
                    )
        elif criteria:
            self.add(
                "rubric.unexpected", task.path, "automated task must not declare Judge criteria"
            )

    def _validate_workspace(self, task: ParsedTask) -> None:
        raw_section = task.sections.get("Workspace Path", "")
        raw_workspace = _first_fenced_block(raw_section).strip()
        if not raw_workspace:
            self.add("workspace.missing", task.path, "Workspace Path section is missing")
            return
        if "\n" in raw_workspace:
            self.add("workspace.path", task.path, "Workspace Path must contain one path")
            return
        pure = PurePosixPath(raw_workspace)
        expected = PurePosixPath(
            "workspace",
            "extension",
            task.category,
            f"task_{task.number:03d}_{task.slug}",
        )
        if pure.is_absolute() or ".." in pure.parts or pure != expected:
            self.add(
                "workspace.path",
                task.path,
                f"Workspace Path must be {expected.as_posix()!r}",
            )
            return
        workspace_dir = self.repo_root.joinpath(*pure.parts)
        if workspace_dir.is_symlink():
            self.add(
                "workspace.symlink",
                workspace_dir,
                "task workspace directory must not be a symlink",
            )
            return
        try:
            resolved = workspace_dir.resolve()
            resolved.relative_to(self.workspace_root.resolve())
        except (OSError, ValueError):
            self.add("workspace.escape", task.path, "Workspace Path escapes workspace/extension")
            return
        task.workspace_dir = workspace_dir
        for child in ("exec", "gt"):
            child_path = workspace_dir / child
            if child_path.is_symlink():
                self.add(
                    "workspace.symlink",
                    child_path,
                    f"workspace {child}/ directory must not be a symlink",
                )
            elif not child_path.is_dir():
                self.add(
                    "workspace.layout", child_path, f"workspace {child}/ directory is missing"
                )

        raw_limit = task.metadata.get("attachment_size_limit_mb", 5)
        limit = _numeric(raw_limit)
        if limit is None or not any(
            _close(limit, allowed) for allowed in ALLOWED_ATTACHMENT_LIMITS_MB
        ):
            self.add(
                "attachment.limit",
                task.path,
                "attachment_size_limit_mb must be 5 or 20 when specified",
            )
            limit = 5.0
        exec_dir = workspace_dir / "exec"
        if exec_dir.is_symlink() or not exec_dir.is_dir():
            return
        allowed_symlinks: dict[str, str] = {}
        gt_path = workspace_dir / "gt" / "expected.json"
        if gt_path.is_file() and not gt_path.is_symlink():
            try:
                gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                gt_data = {}
            if isinstance(gt_data, dict) and isinstance(gt_data.get("allowed_symlinks"), dict):
                allowed_symlinks = {
                    str(relative): str(target)
                    for relative, target in gt_data["allowed_symlinks"].items()
                }
        for attachment in sorted(exec_dir.rglob("*")):
            if attachment.is_symlink():
                relative = attachment.relative_to(exec_dir).as_posix()
                expected_target = allowed_symlinks.get(relative)
                try:
                    actual_target = attachment.readlink().as_posix()
                    resolved = attachment.resolve(strict=False)
                    resolved.relative_to(exec_dir.resolve())
                except (OSError, ValueError):
                    actual_target = None
                if expected_target is None or actual_target != expected_target:
                    self.add(
                        "attachment.symlink",
                        attachment,
                        "attachments must not be symlinks unless declared in gt/expected.json allowed_symlinks and resolved inside exec/",
                    )
                continue
            if not attachment.is_file():
                continue
            try:
                size = attachment.stat().st_size
            except OSError as exc:
                self.add("attachment.stat", attachment, f"cannot read file size: {exc}")
                continue
            if size > int(limit * MIB):
                self.add(
                    "attachment.size",
                    attachment,
                    f"{size} bytes exceeds this task's {limit:g} MiB attachment limit",
                )

    def _validate_prompt_paths_and_urls(self, task: ParsedTask) -> None:
        prompt = task.sections.get("Prompt", "")
        if not prompt:
            self.add("prompt.missing", task.path, "Prompt section is missing or empty")
            return
        workspace_dir = task.workspace_dir
        for raw_path in sorted(set(TMP_WORKSPACE_PATH_RE.findall(prompt))):
            stripped = raw_path.rstrip("/")
            if stripped == "/tmp_workspace":
                continue
            relative = stripped.removeprefix("/tmp_workspace/")
            pure_relative = PurePosixPath(relative)
            if (
                pure_relative.is_absolute()
                or not pure_relative.parts
                or any(part in {"", ".", ".."} for part in pure_relative.parts)
            ):
                self.add(
                    "attachment.path",
                    task.path,
                    f"Prompt path {raw_path!r} must stay within /tmp_workspace",
                )
                continue
            first = pure_relative.parts[0]
            if first == "results":
                continue
            if first == "gt":
                # Existing safety tasks explicitly prohibit reading this path.
                # It is grading data, not an input attachment to resolve.
                if pure_relative.parts == ("gt",):
                    continue
                self.add(
                    "attachment.path",
                    task.path,
                    f"Prompt must not reference grading-data path {raw_path!r}",
                )
                continue
            if workspace_dir is None:
                continue
            exec_dir = workspace_dir / "exec"
            if "*" in relative or "?" in relative:
                exists = any(exec_dir.glob(pure_relative.as_posix()))
            else:
                exists = exec_dir.joinpath(*pure_relative.parts).exists()
            if not exists:
                self.add(
                    "attachment.path",
                    task.path,
                    f"Prompt input path {raw_path!r} is absent from workspace exec/",
                )

        runtime_sources = self.task_records.get(task.task_id, {}).get("runtime_sources", [])
        registered_urls = {
            source.get("url")
            for source in runtime_sources
            if isinstance(source, dict) and isinstance(source.get("url"), str)
        }
        prompt_urls = {url.rstrip(".,;:，。；：") for url in HTTP_URL_RE.findall(prompt)}
        for url in sorted(registered_urls - prompt_urls):
            self.add(
                "url.prompt_missing",
                task.path,
                f"runtime source URL is not present verbatim in Prompt: {url}",
            )
        for url in sorted(prompt_urls - registered_urls):
            self.add(
                "url.unregistered",
                task.path,
                f"Prompt URL is not registered as a runtime source: {url}",
            )

    def _validate_capabilities(self, task: ParsedTask, grading_type: Any) -> None:
        raw_mapping = self.capability_map.get(task.task_id)
        if not isinstance(raw_mapping, dict):
            self.add(
                "capability_map.task",
                self.capability_map_path,
                f"missing checkpoint mapping for {task.task_id}",
            )
            return
        mapped_keys: set[str] = set()
        covered: set[str] = set()
        for key, labels in raw_mapping.items():
            location = f"{self.capability_map_path}:{task.task_id}.{key}"
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", key):
                self.add("capability_map.key", location, "checkpoint key is invalid")
                continue
            mapped_keys.add(key)
            if not isinstance(labels, list) or not 1 <= len(labels) <= 2:
                self.add(
                    "capability_map.count",
                    location,
                    "each checkpoint must map to one or two capabilities",
                )
                continue
            if any(not isinstance(label, str) for label in labels):
                self.add(
                    "capability_map.label", location, "capability labels must be strings"
                )
                continue
            if len(labels) != len(set(labels)):
                self.add(
                    "capability_map.duplicate", location, "capability labels must be unique"
                )
            for label in labels:
                if label not in CAPABILITIES:
                    self.add(
                        "capability_map.label",
                        location,
                        f"unsupported capability {label!r}",
                    )
                else:
                    covered.add(label)
        if not 2 <= len(covered) <= 4:
            self.add(
                "capability_map.coverage",
                self.capability_map_path,
                f"{task.task_id} covers {len(covered)} capabilities; expected 2 to 4",
            )

        auto_keys = task.automated_keys or set()
        rubric_keys = task.rubric_keys or set()
        if grading_type == "hybrid":
            expected_keys = {f"automated.{key}" for key in auto_keys} | {
                f"llm_judge.{key}" for key in rubric_keys
            }
        elif grading_type == "llm_judge":
            expected_keys = {f"llm_judge.{key}" for key in rubric_keys}
        else:
            expected_keys = auto_keys
        missing = expected_keys - mapped_keys
        extra = mapped_keys - expected_keys
        if missing:
            self.add(
                "capability_map.checkpoint_missing",
                self.capability_map_path,
                f"{task.task_id} lacks mapping(s): {sorted(missing)}",
            )
        if extra:
            self.add(
                "capability_map.checkpoint_extra",
                self.capability_map_path,
                f"{task.task_id} has unknown mapping(s): {sorted(extra)}",
            )

    def _validate_mapping_orphans(self, tasks: dict[str, ParsedTask]) -> None:
        registered = set(self.task_records) | set(self.excluded_records)
        for task_id in self.capability_map:
            if not isinstance(task_id, str) or not TASK_ID_RE.fullmatch(task_id):
                continue
            if task_id not in registered:
                self.add(
                    "capability_map.orphan",
                    self.capability_map_path,
                    f"extension-style mapping has no source record: {task_id}",
                )
            elif not self.allow_incomplete and task_id not in tasks:
                # The missing task is already reported by _validate_source_coverage;
                # retaining an ahead-of-time map entry is harmless.
                continue


def validate_repository(
    repo_root: Path, *, allow_incomplete: bool = False
) -> list[ValidationIssue]:
    return ExtensionTaskValidator(repo_root, allow_incomplete=allow_incomplete).validate()


def _find_repo_root(start: Path) -> Path:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "tasks" / "extension").is_dir() and (candidate / "tools").is_dir():
            return candidate
    return current


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_find_repo_root(Path.cwd()),
        help="repository root (default: inferred from the current directory)",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="validate only task files already present; still validate every present task strictly",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    validator = ExtensionTaskValidator(args.repo_root, allow_incomplete=args.allow_incomplete)
    issues = validator.validate()
    if issues:
        print(f"Extension task validation failed with {len(issues)} issue(s):")
        for issue in issues:
            print(f"- {issue.format()}")
        return 1
    mode = "present tasks" if args.allow_incomplete else "registered extension set"
    print(f"Extension task validation passed for {validator.loaded_task_count} {mode}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
