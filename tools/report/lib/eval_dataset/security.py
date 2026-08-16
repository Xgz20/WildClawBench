"""报告输出和静态检查使用的安全边界。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

SECRET_NAME_RE = re.compile(r"(?i)(?:key|token|secret|password|credential)")
ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_VALUE_RE = re.compile(
    # Require a token boundary before sk-/Bearer so ordinary task IDs such
    # as `task-common-zero` are not mistaken for API keys.
    r"(?i)(?<![A-Za-z0-9])(?:bearer\s+|sk-)[A-Za-z0-9._~+/-]{8,}|(?:api[_-]?key|token|secret|password)\s*[=:]\s*[^\s,;]+"
)


def is_env_name(value: str) -> bool:
    return bool(ENV_NAME_RE.fullmatch(value.strip()))


def env_evidence(names: list[str], environ: dict[str, str] | None = None) -> dict[str, str]:
    """仅返回变量名和存在性，不暴露变量值。"""
    env = environ if environ is not None else {}
    return {name: ("present" if name in env else "missing") for name in names}


def redact_text(value: str, max_length: int = 600) -> str:
    value = SECRET_VALUE_RE.sub("[REDACTED]", value)
    value = value[:max_length]
    return value


def sanitize_evidence(value: Any, *, key: str = "") -> Any:
    if SECRET_NAME_RE.search(key):
        if isinstance(value, str):
            return "[REDACTED]"
        return "[REDACTED]" if value is not None else None
    if isinstance(value, dict):
        return {str(k): sanitize_evidence(v, key=str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_evidence(item, key=key) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def dangerous_warmup(text: str) -> list[str]:
    """返回需要人工确认的宿主机危险模式；不执行文本。"""
    patterns = {
        "WARMUP_HOST_DELETE": r"(?:^|\s)(?:rm\s+-rf|rmdir\s+/s|del\s+/s)",
        "WARMUP_HOST_PRIVILEGE": r"(?:^|\s)(?:sudo|doas)\b",
        "WARMUP_HOST_NETWORK": r"(?:^|\s)(?:curl|wget|nc|ssh)\b",
        "WARMUP_HOST_DAEMON": r"(?:docker\s+run|launchctl|systemctl)\b",
    }
    return [code for code, pattern in patterns.items() if re.search(pattern, text, re.I | re.M)]
