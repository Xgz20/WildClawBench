"""彩色 + emoji 日志格式化。

设计（见 docs 讨论）：
- 终端（stdout）：颜色 + emoji，实时观感。
- 文件（run.log）：纯文本 + emoji，无 ANSI 颜色码 —— VS Code 打开干净、
  emoji 作为唯一视觉锚点、grep 不受影响。

emoji 走关键词映射（对消息内容做小写子串匹配），命中不了再按日志级别兜底。
166 处 logger 调用一行不动，仅在此集中处理。
"""
from __future__ import annotations

import logging
import sys

# ANSI 颜色（仅终端 Formatter 使用）
_RESET = "\033[0m"
_DIM = "\033[2m"
_COLOR_BY_LEVEL = {
    logging.DEBUG: "\033[36m",     # cyan
    logging.INFO: "\033[32m",      # green
    logging.WARNING: "\033[33m",   # yellow
    logging.ERROR: "\033[31m",     # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}

# 关键词 → emoji（按顺序匹配，先命中先用；子串、大小写不敏感）。
# 仅用于 INFO/DEBUG；WARNING 及以上按级别固定图标（见 _pick_emoji），
# 以免 warning 里含 "failed" 显示成和 error 相同的 ❌。
# 顺序：具体语义词在前，通用词（starting/start）在后。
_KEYWORD_EMOJI: tuple[tuple[str, str], ...] = (
    ("timed out", "⏱️"),
    ("timeout", "⏱️"),
    ("timed_out", "⏱️"),
    ("cleaned up", "✅"),
    ("finished", "✅"),
    ("complete", "✅"),
    ("container id", "🐳"),
    ("warmup", "🔥"),
    ("grading", "📝"),
    ("grade", "📝"),
    ("token usage", "📊"),
    ("usage written", "📊"),
    ("summary", "📊"),
    ("config written", "🔧"),
    ("skills", "🧩"),
    ("copied", "📁"),
    ("written to", "💾"),
    ("not found", "❌"),
    ("failed", "❌"),
    ("error", "❌"),
    ("skipping", "⏭️"),
    ("skip", "⏭️"),
    ("started", "🚀"),
    ("starting", "🚀"),
    ("start ", "🚀"),
)

# 按级别兜底 / WARNING+ 固定
_LEVEL_EMOJI = {
    logging.DEBUG: "🔍",
    logging.INFO: "ℹ️",
    logging.WARNING: "⚠️",
    logging.ERROR: "❌",
    logging.CRITICAL: "🛑",
}


def _pick_emoji(message: str, level: int) -> str:
    # WARNING 及以上按级别固定醒目图标，保持与 error 的视觉区分
    if level >= logging.WARNING:
        return _LEVEL_EMOJI.get(level, "⚠️")
    lowered = message.lower()
    for keyword, emoji in _KEYWORD_EMOJI:
        if keyword in lowered:
            return emoji
    return _LEVEL_EMOJI.get(level, "ℹ️")


class EmojiFormatter(logging.Formatter):
    """纯文本 + emoji（文件用）。"""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(emoji)s %(message)s",
            datefmt="%H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        record.emoji = _pick_emoji(record.getMessage(), record.levelno)
        return super().format(record)


class ColorEmojiFormatter(logging.Formatter):
    """颜色 + emoji（终端用）。时间戳暗色，级别与正文按级别上色。"""

    def __init__(self) -> None:
        super().__init__(datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        color = _COLOR_BY_LEVEL.get(record.levelno, "")
        emoji = _pick_emoji(record.getMessage(), record.levelno)
        ts = self.formatTime(record, self.datefmt)
        msg = record.getMessage()
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"
        return (
            f"{_DIM}{ts}{_RESET} "
            f"{color}[{record.levelname}]{_RESET} "
            f"{emoji} {color}{msg}{_RESET}"
        )


def configure_console_logging(level: int = logging.INFO) -> None:
    """根 logger 装一个 stdout 彩色+emoji handler（替代 basicConfig）。"""
    root = logging.getLogger()
    root.setLevel(level)
    # ``eval.run_batch`` is imported by grading helpers.  Re-importing it must
    # not attach another stdout handler and duplicate every console line.
    for existing in root.handlers:
        if getattr(existing, "_wildclaw_console_handler", False):
            existing.setLevel(level)
            return
    handler = logging.StreamHandler(sys.stdout)
    handler._wildclaw_console_handler = True
    handler.setFormatter(ColorEmojiFormatter())
    root.addHandler(handler)


def attach_file_logging(log_path, level: int = logging.INFO) -> logging.Handler:
    """给根 logger 追加一个纯文本+emoji 的文件 handler，返回该 handler。"""
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(EmojiFormatter())
    logging.getLogger().addHandler(handler)
    return handler
