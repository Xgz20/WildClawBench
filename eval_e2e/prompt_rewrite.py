"""把用例 Prompt 里的容器内工作区路径改写为桌面端可见的本机路径。

这是端到端与 CLI 侧唯一的输入差异（路径必须真实存在才能执行）。
改写只替换前缀，尾部结构保持不变；映射关系一并返回供结果披露。
"""
from __future__ import annotations

import re
from pathlib import Path

CONTAINER_WORKSPACE = "/tmp_workspace"


def rewrite_prompt(prompt: str, project_dir: Path) -> tuple[str, dict[str, str]]:
    """返回 (改写后的 Prompt, 改写映射)。无匹配时映射为空 dict。

    用 (?![\\w-]) 断言避免误伤 /tmp_workspace_backup 之类的相似前缀。
    """
    target = str(project_dir)
    pattern = re.compile(re.escape(CONTAINER_WORKSPACE) + r"(?![\w-])")
    rewritten, count = pattern.subn(target, prompt)
    if count == 0:
        return prompt, {}
    return rewritten, {CONTAINER_WORKSPACE: target}
