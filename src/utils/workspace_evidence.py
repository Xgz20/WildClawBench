"""Deterministic workspace evidence selection for non-website Judge requests."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any, Mapping


JUDGE_WORKSPACE_EVIDENCE_POLICY_VERSION = "wildclaw-workspace-evidence-v2"
DEFAULT_JUDGE_WORKSPACE_MAX_CHARS = 80_000
DEFAULT_JUDGE_WORKSPACE_FILE_MAX_CHARS = 12_000
DEFAULT_DECLARED_EVIDENCE_FILE_MAX_CHARS = 20_000
CONVENTIONAL_OUTPUT_DIRS = (
    "results",
    "result",
    "output",
    "outputs",
    "artifacts",
    "deliverables",
)
TEXT_EXTENSIONS = {
    ".cfg",
    ".csv",
    ".htm",
    ".html",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".sql",
    ".toml",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
PROTECTED_PARTS = {"gt", ".grading"}


def _declared_items(judge_evidence: Mapping[str, Any] | None) -> list[dict]:
    contract = judge_evidence if isinstance(judge_evidence, Mapping) else {}
    items: list[dict] = []
    for required, key, default_role in (
        (True, "required", "deliverable"),
        (False, "references", "reference"),
    ):
        values = contract.get(key) or []
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, str):
                path = value
                role = default_role
            elif isinstance(value, Mapping):
                path = str(value.get("path") or "")
                role = str(value.get("role") or default_role)
            else:
                continue
            path = path.strip().replace("\\", "/").strip("/")
            if path:
                items.append({
                    "path": path,
                    "role": role,
                    "required": required,
                    "matched": False,
                })
    return items


def _matches_declared(relative_path: str, declaration: str) -> bool:
    normalized = declaration.rstrip("/")
    return (
        relative_path == normalized
        or relative_path.startswith(normalized + "/")
        or fnmatch.fnmatchcase(relative_path, normalized)
    )


def _selection_priority(relative_path: str, declarations: list[dict]) -> tuple[int, str, str]:
    for item in declarations:
        if item["required"] and _matches_declared(relative_path, item["path"]):
            item["matched"] = True
            return 0, "judge_evidence.required", item["role"]
    for item in declarations:
        if not item["required"] and _matches_declared(relative_path, item["path"]):
            item["matched"] = True
            return 1, "judge_evidence.references", item["role"]
    first_part = relative_path.split("/", 1)[0].lower()
    if first_part in CONVENTIONAL_OUTPUT_DIRS:
        return 2, f"conventional_output_dir:{first_part}", "output_candidate"
    return 3, "automatic_discovery", "workspace_file"


def _slice_text(content: str, limit: int) -> tuple[str, list[list[int]], bool]:
    if len(content) <= limit:
        return content, [[0, len(content)]], False
    tail_chars = min(limit // 4, 3_000)
    head_chars = limit - tail_chars
    marker = "\n\n[... middle omitted by workspace evidence budget ...]\n\n"
    selected = content[:head_chars] + marker + content[-tail_chars:]
    return (
        selected,
        [[0, head_chars], [len(content) - tail_chars, len(content)]],
        True,
    )


def collect_workspace_evidence(
    workspace_path: str,
    judge_evidence: Mapping[str, Any] | None = None,
    *,
    max_chars: int = DEFAULT_JUDGE_WORKSPACE_MAX_CHARS,
    per_file_max_chars: int = DEFAULT_JUDGE_WORKSPACE_FILE_MAX_CHARS,
) -> dict:
    """Collect prioritized text plus a manifest excluding protected grading dirs."""
    workspace = Path(workspace_path)
    declarations = _declared_items(judge_evidence)
    manifest: list[dict] = []

    if workspace.is_dir():
        for path in sorted(workspace.rglob("*")):
            try:
                relative = path.relative_to(workspace).as_posix()
            except ValueError:
                continue
            parts = Path(relative).parts
            if any(part in PROTECTED_PARTS for part in parts):
                continue
            if path.is_symlink():
                manifest.append({
                    "path": relative,
                    "status": "omitted",
                    "reason": "symlink_not_followed",
                })
                continue
            if not path.is_file():
                continue
            try:
                original_bytes = path.stat().st_size
            except OSError:
                original_bytes = None
            priority, reason, role = _selection_priority(relative, declarations)
            manifest.append({
                "path": relative,
                "priority": priority,
                "selection_reason": reason,
                "role": role,
                "original_bytes": original_bytes,
                "status": "pending",
            })

    remaining = max(0, int(max_chars))
    selected_blocks: list[str] = []
    for item in sorted(
        (entry for entry in manifest if entry["status"] == "pending"),
        key=lambda entry: (entry["priority"], entry["path"]),
    ):
        path = workspace / item["path"]
        explicit = item["priority"] <= 1
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            item.update(status="omitted", reason="unsupported_text_extension")
            continue
        if remaining <= 0:
            item.update(status="omitted", reason="workspace_char_budget_exhausted")
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            item.update(status="unreadable", reason=type(exc).__name__)
            continue
        original_chars = len(content)
        file_limit = min(per_file_max_chars, remaining)
        if explicit:
            file_limit = min(
                max(per_file_max_chars, DEFAULT_DECLARED_EVIDENCE_FILE_MAX_CHARS),
                remaining,
            )
        included, ranges, truncated = _slice_text(content, file_limit)
        item.update({
            "status": "selected",
            "original_chars": original_chars,
            "included_chars": sum(end - start for start, end in ranges),
            "included_ranges": ranges,
            "truncated": truncated,
        })
        selected_blocks.append(
            f"### {item['path']}\n"
            f"[evidence: {item['selection_reason']}; "
            f"included_chars={item['included_chars']}; "
            f"original_chars={original_chars}; truncated={str(truncated).lower()}]\n"
            f"{included}"
        )
        remaining -= len(included)

    missing_required = [
        {"path": item["path"], "role": item["role"]}
        for item in declarations
        if item["required"] and not item["matched"]
    ]
    missing_references = [
        {"path": item["path"], "role": item["role"]}
        for item in declarations
        if not item["required"] and not item["matched"]
    ]
    selected = sorted(
        (item for item in manifest if item["status"] == "selected"),
        key=lambda item: (item["priority"], item["path"]),
    )
    omitted = [item for item in manifest if item["status"] != "selected"]
    notes = [
        f"Evidence policy: {JUDGE_WORKSPACE_EVIDENCE_POLICY_VERSION}",
        f"Selected files: {len(selected)}; omitted/unreadable files: {len(omitted)}.",
    ]
    if missing_required:
        notes.append(
            "Missing required evidence: "
            + ", ".join(item["path"] for item in missing_required)
        )
    if missing_references:
        notes.append(
            "Missing declared references: "
            + ", ".join(item["path"] for item in missing_references)
        )
    text = "\n".join(notes)
    if selected_blocks:
        text += "\n\n" + "\n\n".join(selected_blocks)

    return {
        "text": text,
        "metadata": {
            "policy": JUDGE_WORKSPACE_EVIDENCE_POLICY_VERSION,
            "max_chars": max_chars,
            "per_file_max_chars": per_file_max_chars,
            "declared_file_max_chars": max(
                per_file_max_chars, DEFAULT_DECLARED_EVIDENCE_FILE_MAX_CHARS
            ),
            "priority_order": [
                "judge_evidence.required",
                "judge_evidence.references",
                "conventional_output_dirs",
                "automatic_discovery",
            ],
            "declared": {
                "required": [
                    {"path": item["path"], "role": item["role"]}
                    for item in declarations if item["required"]
                ],
                "references": [
                    {"path": item["path"], "role": item["role"]}
                    for item in declarations if not item["required"]
                ],
            },
            "selected": selected,
            "omitted": omitted,
            "manifest": manifest,
            "missing_required": missing_required,
            "missing_references": missing_references,
            "selected_file_count": len(selected),
            "omitted_file_count": len(omitted),
            "included_chars": max_chars - remaining,
        },
    }
