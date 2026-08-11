"""端到端评测 manifest 的读写与路径解析。

manifest 内仓库路径与 project_dir 一律存相对路径，运行时按 --e2e-root /
仓库根重新解析，换机器只需换入口参数。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

HARNESS_NAME = "astroncode-desktop"

STATUS_PENDING = "pending"
STATUS_COLLECTED = "collected"
STATUS_GRADED = "graded"
STATUS_TRACE_MISSING = "trace_missing"


@dataclass
class RunEntry:
    task_id: str
    category: str
    task_file: str
    workspace_src: str
    project_dir: str
    model: str
    reasoning_effort: str
    prompt_rewritten: bool
    prompt_rewrite_map: dict[str, str] = field(default_factory=dict)
    status: str = STATUS_PENDING
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunEntry":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class Manifest:
    e2e_root: str
    created_at: str
    round: str = "round-1"  # 轮次标识（如 round-1, round-2）
    runs: list[RunEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "e2e_root": self.e2e_root,
            "created_at": self.created_at,
            "round": self.round,
            "runs": [r.to_dict() for r in self.runs],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        return cls(
            e2e_root=data.get("e2e_root", ""),
            created_at=data.get("created_at", ""),
            round=data.get("round", "round-1"),  # 兼容旧 manifest（无 round 字段）
            runs=[RunEntry.from_dict(r) for r in data.get("runs", [])],
        )


def save_manifest(manifest: Manifest, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_manifest(path: Path) -> Manifest:
    return Manifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def resolve_project_dir(entry: RunEntry, e2e_root: Path) -> Path:
    p = Path(entry.project_dir)
    return p if p.is_absolute() else (Path(e2e_root) / p)


def resolve_repo_path(rel: str, repo_root: Path) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else (Path(repo_root) / p)
