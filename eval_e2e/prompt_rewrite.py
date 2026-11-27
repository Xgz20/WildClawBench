"""把用例 Prompt 里的容器内工作区路径改写为桌面端可见的本机路径。

改写只替换前缀，尾部结构保持不变；映射关系一并返回供结果披露。
"""
from __future__ import annotations

from pathlib import Path
from src.wildclawbench_workspace import rewrite_root

CONTAINER_WORKSPACE = "/tmp_workspace"


def rewrite_prompt(prompt: str, project_dir: Path) -> tuple[str, dict[str, str]]:
    """返回 (改写后的 Prompt, 改写映射)。无匹配时映射为空 dict。

    同一匹配规则兼容中文紧邻根目录，并保护相似目录名。
    """
    target = str(project_dir)
    return rewrite_root(prompt, target)
