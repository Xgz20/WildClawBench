from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

import yaml

load_dotenv()
# Resolve task-relative paths from repository root, not src/.
ROOT_DIR = Path(__file__).resolve().parents[2]
METRIC_PROFILE_PRIMARY_DIMENSIONS = {
    "web-site-gen": {
        "content_structure",
        "interaction_function",
        "visual_layout",
    },
    "ppt": set(),
}


def normalize_tags(raw) -> list[str]:
    """Coerce a frontmatter `tags` value into a clean, deduplicated str list.

    Accepts a YAML list or a comma-separated string; each tag is trimmed and
    lower-cased so matching is case-insensitive. Order is preserved.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        items = raw
    else:
        items = [raw]
    seen: dict[str, None] = {}
    for item in items:
        tag = str(item).strip().lower()
        if tag:
            seen.setdefault(tag, None)
    return list(seen.keys())


def resolve_metric_profile(tags: list[str]) -> str:
    """Resolve the single specialized metric protocol selected by task tags."""
    profiles = [tag for tag in tags if tag in METRIC_PROFILE_PRIMARY_DIMENSIONS]
    if len(profiles) > 1:
        raise ValueError(f"Task declares multiple metric profiles: {profiles}")
    return profiles[0] if profiles else ""


def parse_rubric_criteria(rubric_text: str) -> list[dict]:
    """Parse `## LLM Judge Rubric` into an ordered list of criteria.

    Each criterion heading follows the v2 format. Website tasks may add stable
    dimension keys while existing tasks keep the original two-field form:
        ### Criterion N: <名称> (key: <stable_key>, weight: <0.X>)
        ### Criterion N: <名称> (key: <stable_key>, primary: <key>, secondary: <key>, weight: <0.X>)
    followed by `**Score 1.0**: ...` band descriptions.

    Returns a list preserving document order; each item is:
        {"key": str, "primary": str, "secondary": str,
         "weight": float, "name": str, "rubric": str}
    `rubric` is the full band-description text belonging to that criterion,
    used verbatim in the judge prompt. Headings that don't match the format
    are skipped (so free-form rubrics degrade gracefully to an empty list,
    which routes the task through the legacy path).
    """
    if not rubric_text:
        return []
    heading_re = re.compile(r"^###\s+(.*?)\s*\((.*?)\)\s*$")
    metadata_re = re.compile(
        r"(?:^|,)\s*(key|primary|secondary|weight)\s*:\s*([^,]+)\s*"
    )
    stable_key_re = re.compile(r"^[A-Za-z0-9_\-]+$")
    criteria: list[dict] = []
    cur: Optional[dict] = None
    body: list[str] = []
    for line in rubric_text.split("\n"):
        m = heading_re.match(line.strip())
        metadata = {
            key: value.strip()
            for key, value in metadata_re.findall(m.group(2))
        } if m else {}
        key = metadata.get("key", "")
        weight = metadata.get("weight", "")
        try:
            parsed_weight = float(weight)
        except ValueError:
            parsed_weight = None
        if m and stable_key_re.fullmatch(key) and parsed_weight is not None:
            if cur is not None:
                cur["rubric"] = "\n".join(body).strip()
                criteria.append(cur)
            name = re.sub(
                r"^(?:Criterion\s+\d+\s*[:：]\s*)?", "", m.group(1)
            ).strip()
            cur = {
                "key": key,
                "primary": metadata.get("primary", ""),
                "secondary": metadata.get("secondary", ""),
                "weight": parsed_weight,
                "name": name,
                "rubric": "",
            }
            body = [line]
        elif cur is not None:
            body.append(line)
    if cur is not None:
        cur["rubric"] = "\n".join(body).strip()
        criteria.append(cur)
    return criteria


def parse_task_md(task_file: Path) -> dict:
    """Extract task_id, prompt, workspace_path, and automated_checks from task.md."""
    content = task_file.read_text(encoding="utf-8")

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not fm_match:
        raise ValueError(f"YAML frontmatter not found: {task_file}")

    metadata = yaml.safe_load(fm_match.group(1))
    body     = fm_match.group(2)

    sections: dict[str, str] = {}
    current_section: Optional[str] = None
    lines: list[str] = []
    for line in body.split("\n"):
        header = re.match(r"^##\s+(.+)$", line)
        if header:
            if current_section is not None:
                sections[current_section] = "\n".join(lines).strip()
            current_section = header.group(1)
            lines = []
        else:
            lines.append(line)
    if current_section is not None:
        sections[current_section] = "\n".join(lines).strip()

    def strip_codeblock(raw: str) -> str:
        # Extract the first fenced block if present, so trailing content after
        # the closing ``` (e.g. a `---` horizontal rule separating sections, as
        # used in v2 task templates) does not leak into the code. Falls back to
        # the plain opening/closing-fence strip when no full fence pair exists.
        s = raw.strip()
        m = re.search(r"```[^\n]*\n(.*?)\n```", s, re.DOTALL)
        if m:
            return m.group(1).strip()
        s = re.sub(r"^```[^\n]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
        return s

    prompt = sections.get("Prompt", "").strip()

    raw_workspace  = sections.get("Workspace Path", "").strip()
    workspace_path = strip_codeblock(raw_workspace)
    if not workspace_path:
        raise ValueError(f"Missing ## Workspace Path in task.md: {task_file}")

    skills_path = "skills"

    automated_checks = strip_codeblock(sections.get("Automated Checks", ""))
    env    = strip_codeblock(sections.get("Env",    ""))
    skills = strip_codeblock(sections.get("Skills",    ""))
    warmup = strip_codeblock(sections.get("Warmup", ""))

    # v2 format: LLM Judge Rubric section + grading config from frontmatter.
    # Empty rubric_criteria routes the task through the legacy grading path.
    llm_judge_rubric = sections.get("LLM Judge Rubric", "").strip()
    rubric_criteria = parse_rubric_criteria(llm_judge_rubric)
    grading_type = str(metadata.get("grading_type", "")).strip()
    tags = normalize_tags(metadata.get("tags"))
    metric_profile = resolve_metric_profile(tags)
    if metric_profile == "web-site-gen":
        declared_criteria = len(re.findall(
            r"^###\s+Criterion\s+\d+\s*[:：]", llm_judge_rubric, re.MULTILINE
        ))
        if declared_criteria != len(rubric_criteria):
            raise ValueError(
                f"Website task rubric declares {declared_criteria} criteria but "
                f"parsed {len(rubric_criteria)}: {task_file}"
            )
        keys = [criterion["key"] for criterion in rubric_criteria]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Website task rubric contains duplicate keys: {task_file}")
        if any(
            not criterion.get("primary") or not criterion.get("secondary")
            for criterion in rubric_criteria
        ):
            raise ValueError(
                f"Website task rubric criteria require primary and secondary: {task_file}"
            )
        invalid_primary = sorted({
            criterion["primary"]
            for criterion in rubric_criteria
            if criterion["primary"]
            not in METRIC_PROFILE_PRIMARY_DIMENSIONS[metric_profile]
        })
        if invalid_primary:
            raise ValueError(
                f"Website task rubric contains unsupported primary dimensions "
                f"{invalid_primary}: {task_file}"
            )
    grading_weights = metadata.get("grading_weights") or {}
    if not isinstance(grading_weights, dict):
        grading_weights = {}

    task_id         = metadata.get("id",             task_file.stem)
    timeout_seconds = int(metadata.get("timeout_seconds", 120))

    wp = Path(workspace_path)
    if not wp.is_absolute():
        wp = (ROOT_DIR / wp).resolve()
    workspace_path = str(wp)

    sp = Path(skills_path)
    if not sp.is_absolute():
        sp = (ROOT_DIR / sp).resolve()
    skills_path = str(sp)

    return {
        "task_id":          task_id,
        "prompt":           prompt,
        "workspace_path":   workspace_path,
        "skills_path":      skills_path,
        "automated_checks": automated_checks,
        "env":              env,
        "skills":           skills,
        "warmup":           warmup,
        "timeout_seconds":  timeout_seconds,
        "file_path":        str(task_file.resolve()),
        "category":         task_file.parent.name,
        "modality":         str(metadata.get("modality", "")).strip(),
        "tags":             tags,
        "metric_profile":   metric_profile,
        # v2 fields for hybrid grading separation
        "grading_type":     grading_type,
        "grading_weights":  grading_weights,
        "llm_judge_rubric": llm_judge_rubric,
        "rubric_criteria":  rubric_criteria,
    }
