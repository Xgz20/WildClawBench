"""任务 Markdown 的不执行解析。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .security import dangerous_warmup


class DuplicateKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: DuplicateKeyLoader, node: yaml.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark, f"duplicate key: {key}", key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


DuplicateKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


@dataclass
class TaskDocument:
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    sections: dict[str, str] = field(default_factory=dict)
    raw: str = ""
    frontmatter_error: str = ""

    @property
    def task_id(self) -> str:
        return str(self.metadata.get("id") or self.path.stem)

    @property
    def category(self) -> str:
        return str(self.metadata.get("category") or self.path.parent.name)

    def section(self, name: str) -> str:
        return self.sections.get(name, "").strip()


def strip_codeblock(value: str) -> str:
    value = value.strip()
    match = re.search(r"```[^\n]*\n(.*?)\n```", value, re.DOTALL)
    if match:
        return match.group(1).strip()
    return re.sub(r"^```[^\n]*\n?", "", re.sub(r"\n?```$", "", value)).strip()


def parse_task_document(path: str | Path) -> TaskDocument:
    path = Path(path).resolve()
    raw = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.DOTALL)
    if not match:
        return TaskDocument(path=path, raw=raw, frontmatter_error="YAML frontmatter not found")
    metadata: dict[str, Any] = {}
    error = ""
    try:
        loaded = yaml.load(match.group(1), Loader=DuplicateKeyLoader)
        if not isinstance(loaded, dict):
            error = "YAML frontmatter must be a mapping"
        else:
            metadata = loaded
    except yaml.YAMLError as exc:
        error = str(exc).splitlines()[0]
    sections: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in match.group(2).splitlines():
        header = re.match(r"^##\s+(.+?)\s*$", line)
        if header:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = header.group(1).strip()
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return TaskDocument(path=path, metadata=metadata, sections=sections, raw=raw, frontmatter_error=error)


def extract_env_names(text: str) -> tuple[list[str], list[str]]:
    names: list[str] = []
    invalid: list[str] = []
    for raw in strip_codeblock(text).splitlines():
        line = raw.strip().strip("`- ")
        if not line or line.startswith("#"):
            continue
        # Accept KEY, KEY=..., KEY: ... and shell exports while never reading values.
        line = re.sub(r"^(?:export\s+)?", "", line)
        name = re.split(r"[=:\s]", line, maxsplit=1)[0]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            names.append(name)
        else:
            invalid.append(name or line)
    return names, invalid


def extract_skill_names(text: str) -> list[str]:
    names: list[str] = []
    for raw in strip_codeblock(text).splitlines():
        line = raw.strip().strip("`- ")
        if line and not line.startswith("#"):
            names.append(line.split()[0])
    return names


def extract_warmup_commands(text: str) -> list[str]:
    value = strip_codeblock(text)
    return [line.strip() for line in value.splitlines() if line.strip() and not line.strip().startswith("#")]


def ast_grade_info(code: str) -> tuple[bool, list[str], str]:
    if not code.strip():
        return False, [], "Automated Checks 为空"
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return False, [], f"Automated Checks Python 语法错误: {exc.msg}"
    grades = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "grade"]
    if not grades:
        return False, [], "Automated Checks 未定义 grade()"
    keys: list[str] = []
    for node in ast.walk(grades[0]):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]*", node.value) and node.value not in keys:
                keys.append(node.value)
    return True, keys, ""


def rubric_info(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    criteria: list[dict[str, Any]] = []
    errors: list[str] = []
    heading = re.compile(r"^###\s+(.*?)\s*\((.*?)\)\s*$")
    meta = re.compile(r"(?:^|,)\s*(key|weight|primary|secondary)\s*:\s*([^,]+)")
    for line in text.splitlines():
        match = heading.match(line.strip())
        if not match:
            continue
        values = {key: value.strip() for key, value in meta.findall(match.group(2))}
        if "key" not in values:
            continue
        try:
            weight = float(values.get("weight", "1"))
        except ValueError:
            errors.append(f"rubric weight 非数字: {values.get('weight')}")
            weight = 0.0
        criteria.append({"key": values["key"], "weight": weight, "name": match.group(1)})
    keys = [item["key"] for item in criteria]
    if len(keys) != len(set(keys)):
        errors.append("rubric key 重复")
    return criteria, errors


def warmup_info(text: str) -> dict[str, Any]:
    commands = extract_warmup_commands(text)
    return {"commands": commands, "dangerous_codes": dangerous_warmup("\n".join(commands))}
