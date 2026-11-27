"""Portable workspace names; never resolve or rewrite candidate file contents."""
from __future__ import annotations

import re

PROFILE = "wildclawbench.workspace-paths/v1"
LOGICAL_ROOT = "/tmp_workspace"
WINDOWS_ROOT = r"C:\ProgramData\WGUI\workspace\project"
WINDOWS_ALIAS = r"C:\tmp_workspace"


def rewrite_root(text: str, target: str, *, source: str = LOGICAL_ROOT):
    """Match a complete logical root, including adjacent Chinese prose.

    ASCII identifier boundaries preserve _backup, -backup and _eval. The left
    boundary also excludes nested paths and URL paths. Callable replacement
    preserves literal Windows backslashes (including \\t and \\1).
    """
    pattern = re.compile(r"(?<![A-Za-z0-9_./:\\-])" + re.escape(source) + r"(?![A-Za-z0-9_-])")
    result, count = pattern.subn(lambda _: target, text)
    return result, ({source: target} if count else {})


def strip_workspace_root(value: str, *, roots=()):
    """Strip only known absolute workspace roots; preserve the relative suffix.

    This is a lexical field parser, not permission to access a file. Callers
    retain their existing traversal, prefix, symlink and ordinary-file checks.
    Unknown drives/UNC paths and lookalike root names remain absolute.
    """
    text = value.replace("\\", "/")
    for root in (LOGICAL_ROOT, WINDOWS_ALIAS, WINDOWS_ROOT, *roots):
        root = str(root).replace("\\", "/").rstrip("/")
        windows = bool(re.match(r"^[A-Za-z]:/", root))
        compared, expected = (text.casefold(), root.casefold()) if windows else (text, root)
        if compared == expected:
            return "."
        if compared.startswith(expected + "/"):
            return text[len(root) + 1:]
    return text


def relative_workspace_path(value, *, roots=()):
    """Return a portable member name, rejecting ambiguous/escaping paths."""
    if not isinstance(value, str) or not value or "\0" in value:
        return None
    text = strip_workspace_root(value, roots=roots)
    if text.startswith("/") or ":" in text or ".." in text.split("/"):
        return None
    parts = [part for part in text.split("/") if part not in {"", "."}]
    return "/".join(parts) if parts else None


def environment_note(platform: str, *, workspace: str | None = None):
    """Execution-only context; task semantics and public assets stay unchanged."""
    if platform == "windows":
        return ("[执行环境]\n操作系统：Windows；默认终端：PowerShell。当前工作区：" + (workspace or WINDOWS_ROOT)
                + "。逻辑路径 /tmp_workspace 对应此工作区，也可使用当前目录下的相对路径。\n"
                "Prompt 中的 python3、bash 或 POSIX 命令是示例，请先确认本机解释器，使用 Python 3 / PowerShell 的等价命令；"
                "不要假设存在 bash 或 python3 命令。文件内容与业务要求仍按题目执行。\n"
                "产物中的文件引用优先采用工作区相对路径；题目要求绝对路径时可使用 /tmp_workspace 逻辑路径或本机实际工作区路径。\n\n")
    if platform == "linux":
        return ("[执行环境]\n操作系统：Linux；工作区：" + (workspace or LOGICAL_ROOT)
                + "。Python 3 命令：python3。题目中的 /tmp_workspace 表示此工作区；产物中的文件引用优先采用工作区相对路径，"
                "题目明确要求绝对路径时遵循题目。\n\n")
    raise ValueError("UNSUPPORTED_WORKSPACE_PLATFORM: " + platform)
