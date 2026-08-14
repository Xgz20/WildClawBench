from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode
from yaml.tokens import (
    AliasToken,
    BlockEndToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
    ScalarToken,
    ValueToken,
)


DSH_SKILLS_DIR = "/root/.dsh/skills"
_DSH_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_YAML_12_NULL = re.compile(r"^(?:~|null|Null|NULL)?$")
_YAML_12_BOOLEAN = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
_YAML_12_INT = re.compile(
    r"^(?:[-+]?0o[0-7]+|[-+]?0x[0-9a-fA-F]+|[-+]?[0-9]+)$"
)
_YAML_12_FLOAT = re.compile(
    r"^(?:[-+]?(?:(?:(?:[0-9]+)?\.[0-9]+|[0-9]+\.)"
    r"(?:[eE][-+]?[0-9]+)?|[0-9]+[eE][-+]?[0-9]+)|"
    r"[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)
_YAML_NULL_TAG = "tag:yaml.org,2002:null"
_YAML_BOOL_TAG = "tag:yaml.org,2002:bool"
_YAML_INT_TAG = "tag:yaml.org,2002:int"
_YAML_FLOAT_TAG = "tag:yaml.org,2002:float"
_YAML_STRING_TAG = "tag:yaml.org,2002:str"
logger = logging.getLogger(__name__)


class _Yaml12CoreLoader(yaml.BaseLoader):
    pass


_Yaml12CoreLoader.add_implicit_resolver(
    _YAML_NULL_TAG,
    _YAML_12_NULL,
    ["~", "n", "N", ""],
)
_Yaml12CoreLoader.add_implicit_resolver(
    _YAML_BOOL_TAG,
    _YAML_12_BOOLEAN,
    list("tTfF"),
)
_Yaml12CoreLoader.add_implicit_resolver(
    _YAML_INT_TAG,
    _YAML_12_INT,
    list("-+0123456789"),
)
_Yaml12CoreLoader.add_implicit_resolver(
    _YAML_FLOAT_TAG,
    _YAML_12_FLOAT,
    list("-+0123456789."),
)


class DshSkillError(ValueError):
    """Raised when a declared task skill cannot be installed for DSH."""


class _DshSkillNotFound(DshSkillError):
    """Raised when a task declaration refers to an absent skill bundle."""


@dataclass(frozen=True)
class _SkillBundle:
    source: Path
    normalized_name: str


@dataclass(frozen=True)
class _ParsedSkill:
    raw: str
    name: str
    name_start: int
    name_end: int


def normalize_dsh_skill_name(name: str) -> str:
    normalized = _NON_ALPHANUMERIC.sub("-", name.strip().lower()).strip("-")
    if not normalized or not _DSH_SKILL_NAME.fullmatch(normalized):
        raise DshSkillError(f"skill name {name!r} cannot be normalized for DSH")
    return normalized


def build_dsh_prompt(base_prompt: str, skill_names: list[str]) -> str:
    if not skill_names:
        return base_prompt
    gestures = "\n".join(f"/{name}" for name in skill_names)
    return f"{gestures}\n\n{base_prompt}"


def _top_level_value_token_indices(frontmatter: str) -> list[int]:
    tokens = list(yaml.scan(frontmatter, Loader=_Yaml12CoreLoader))
    collection_starts = (
        BlockMappingStartToken,
        BlockSequenceStartToken,
        FlowMappingStartToken,
        FlowSequenceStartToken,
    )
    collection_ends = (
        BlockEndToken,
        FlowMappingEndToken,
        FlowSequenceEndToken,
    )
    stack: list[type] = []
    root_depth: int | None = None
    value_indices: list[int] = []
    for index, token in enumerate(tokens):
        if isinstance(token, collection_starts):
            stack.append(type(token))
            if root_depth is None and isinstance(
                token, (BlockMappingStartToken, FlowMappingStartToken)
            ):
                root_depth = len(stack)
        elif isinstance(token, collection_ends):
            if stack:
                stack.pop()
        elif (
            isinstance(token, ValueToken)
            and root_depth is not None
            and len(stack) == root_depth
        ):
            value_indices.append(index)
    return value_indices


def _value_token_span(frontmatter: str, pair_index: int) -> tuple[int, int]:
    tokens = list(yaml.scan(frontmatter, Loader=_Yaml12CoreLoader))
    value_indices = _top_level_value_token_indices(frontmatter)
    if pair_index >= len(value_indices):
        raise DshSkillError("failed to locate skill name value in YAML frontmatter")
    value_index = value_indices[pair_index]

    value_token = next(
        (
            token
            for token in tokens[value_index + 1 :]
            if isinstance(token, (ScalarToken, AliasToken))
        ),
        None,
    )
    if value_token is None:
        raise DshSkillError("failed to locate skill name scalar in YAML frontmatter")
    start = value_token.start_mark.index
    end = value_token.end_mark.index
    if isinstance(value_token, ScalarToken) and value_token.style in {"|", ">"}:
        block_text = frontmatter[start:end]
        if block_text.endswith("\r\n"):
            end -= 2
        elif block_text.endswith(("\n", "\r")):
            end -= 1
    return start, end


def _reject_duplicate_mapping_keys(
    node: Node,
    path: Path,
    seen_nodes: set[int] | None = None,
) -> None:
    if seen_nodes is None:
        seen_nodes = set()
    node_id = id(node)
    if node_id in seen_nodes:
        return
    seen_nodes.add(node_id)
    if isinstance(node, MappingNode):
        seen_keys: set[tuple[str, object]] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, ScalarNode):
                key_identity = _yaml_scalar_identity(key_node)
                if key_identity in seen_keys:
                    raise DshSkillError(
                        f"skill file {path} has duplicate YAML mapping key {key_node.value!r}"
                    )
                seen_keys.add(key_identity)
            _reject_duplicate_mapping_keys(key_node, path, seen_nodes)
            _reject_duplicate_mapping_keys(value_node, path, seen_nodes)
    elif isinstance(node, SequenceNode):
        for child in node.value:
            _reject_duplicate_mapping_keys(child, path, seen_nodes)


def _yaml_scalar_identity(node: ScalarNode) -> tuple[str, object]:
    """Match yaml@2 duplicate-key equality for YAML 1.2 core scalar keys."""
    value = node.value
    if node.tag == _YAML_NULL_TAG:
        return ("null", None)
    if node.tag == _YAML_BOOL_TAG:
        return ("boolean", value.lower() == "true")
    if node.tag == _YAML_INT_TAG:
        sign = -1 if value.startswith("-") else 1
        unsigned = value[1:] if value[:1] in {"-", "+"} else value
        if unsigned.startswith("0o"):
            number = int(unsigned[2:], 8)
        elif unsigned.startswith("0x"):
            number = int(unsigned[2:], 16)
        else:
            number = int(unsigned, 10)
        return ("number", sign * number)
    if node.tag == _YAML_FLOAT_TAG:
        lower = value.lower()
        if lower.endswith(".nan"):
            # JavaScript NaN is not equal to itself, so yaml@2 permits repeated NaN keys.
            return ("nan", id(node))
        if lower.endswith(".inf"):
            number = float("-inf") if lower.startswith("-") else float("inf")
        else:
            number = float(value)
        return ("number", number)
    return (node.tag, value)


def _parse_skill(path: Path) -> _ParsedSkill:
    try:
        raw = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DshSkillError(f"failed to read skill file {path}: {exc}") from exc

    lines = raw.splitlines(keepends=True)
    if not lines or lines[0] not in {"---\n", "---\r\n"}:
        raise DshSkillError(f"skill file {path} is missing YAML frontmatter")
    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line in {"---", "---\n", "---\r\n"}
        ),
        None,
    )
    if closing_index is None:
        raise DshSkillError(f"skill file {path} has unterminated YAML frontmatter")

    frontmatter_offset = len(lines[0])
    frontmatter = "".join(lines[1:closing_index])
    try:
        document = yaml.compose(frontmatter, Loader=_Yaml12CoreLoader)
    except yaml.YAMLError as exc:
        raise DshSkillError(f"skill file {path} has invalid YAML frontmatter: {exc}") from exc
    if not isinstance(document, MappingNode):
        raise DshSkillError(f"skill file {path} frontmatter must be a YAML mapping")
    _reject_duplicate_mapping_keys(document, path)

    fields: dict[str, tuple[int, ScalarNode]] = {}
    for pair_index, (key_node, value_node) in enumerate(document.value):
        if not isinstance(key_node, ScalarNode):
            continue
        if key_node.value in {"name", "description"}:
            if not isinstance(value_node, ScalarNode) or value_node.tag != _YAML_STRING_TAG:
                raise DshSkillError(
                    f"skill file {path} frontmatter requires a string {key_node.value}"
                )
            fields[key_node.value] = (pair_index, value_node)

    name_field = fields.get("name")
    description_field = fields.get("description")
    if name_field is None or not name_field[1].value.strip():
        raise DshSkillError(f"skill file {path} frontmatter requires a string name")
    if description_field is None or not description_field[1].value.strip():
        raise DshSkillError(f"skill file {path} frontmatter requires a string description")
    name_start, name_end = _value_token_span(frontmatter, name_field[0])
    return _ParsedSkill(
        raw=raw,
        name=name_field[1].value,
        name_start=frontmatter_offset + name_start,
        name_end=frontmatter_offset + name_end,
    )


def _render_staged_skill(
    parsed: _ParsedSkill,
    normalized_name: str,
    container_bundle_dir: str,
) -> str:
    staged = (
        parsed.raw[: parsed.name_start]
        + normalized_name
        + parsed.raw[parsed.name_end :]
    )
    return staged.replace("{baseDir}", container_bundle_dir)


def _resolve_bundle(skills_root: Path, declaration: str) -> tuple[Path, Path]:
    relative = declaration.replace("\\", "/").strip("/")
    if not relative:
        raise DshSkillError("skill declaration must not be empty")
    source = (skills_root / relative).resolve()
    try:
        source.relative_to(skills_root)
    except ValueError as exc:
        raise DshSkillError(
            f"skill declaration {declaration!r} escapes skills root {skills_root}"
        ) from exc
    skill_file = source / "SKILL.md"
    if skill_file.is_symlink():
        raise DshSkillError(f"skill file {skill_file}: SKILL.md must not be a symlink")
    if not source.is_dir() or not skill_file.is_file():
        raise _DshSkillNotFound(f"declared skill bundle not found: {source}")
    return source, skill_file


def _docker_run(command: list[str], operation: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise DshSkillError(f"{operation} failed{suffix}")


def install_dsh_skills(
    task_id: str,
    skills: str,
    skills_path: str,
    *,
    container_skills_root: str = DSH_SKILLS_DIR,
    on_missing: Callable[[str], None] | None = None,
) -> list[str]:
    skills_root = Path(skills_path).expanduser().resolve()
    bundles: list[_SkillBundle] = []
    seen: dict[str, str] = {}

    for declaration in (line.strip() for line in skills.splitlines()):
        if not declaration:
            continue
        try:
            source, skill_file = _resolve_bundle(skills_root, declaration)
        except _DshSkillNotFound as exc:
            logger.warning("[%s] %s, skipping", task_id, exc)
            if on_missing is not None:
                on_missing(declaration)
            continue
        parsed = _parse_skill(skill_file)
        normalized_name = normalize_dsh_skill_name(parsed.name)
        previous = seen.get(normalized_name)
        if previous is not None:
            raise DshSkillError(
                "normalized skill name collision "
                f"{normalized_name!r}: {previous!r} and {declaration!r}"
            )
        seen[normalized_name] = declaration
        bundles.append(_SkillBundle(source, normalized_name))

    if not bundles:
        return []

    container_root = container_skills_root.rstrip("/")
    _docker_run(
        ["docker", "exec", task_id, "mkdir", "-p", container_root],
        "DSH skills root creation",
    )
    with tempfile.TemporaryDirectory(prefix="wildclaw-dsh-skills-") as temp_dir:
        staging_root = Path(temp_dir)
        for bundle in bundles:
            staged_bundle = staging_root / bundle.normalized_name
            shutil.copytree(bundle.source, staged_bundle, symlinks=True)
            parsed = _parse_skill(staged_bundle / "SKILL.md")
            container_bundle_dir = f"{container_root}/{bundle.normalized_name}"
            (staged_bundle / "SKILL.md").write_bytes(
                _render_staged_skill(
                    parsed,
                    bundle.normalized_name,
                    container_bundle_dir,
                ).encode("utf-8")
            )
            _docker_run(
                ["docker", "exec", task_id, "mkdir", "-p", container_bundle_dir],
                f"DSH skill directory creation for {bundle.normalized_name}",
            )
            _docker_run(
                [
                    "docker",
                    "cp",
                    f"{staged_bundle}/.",
                    f"{task_id}:{container_bundle_dir}/",
                ],
                f"DSH skill install for {bundle.normalized_name}",
            )

    return [bundle.normalized_name for bundle in bundles]
