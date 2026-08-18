from __future__ import annotations

import json


DEFAULT_MAX_SCREENSHOTS = 8
DEFAULT_MAX_IMAGE_BYTES = 12 * 1024 * 1024


def build_website_evidence_code(
    workspace_path: str,
    *,
    max_screenshots: int = DEFAULT_MAX_SCREENSHOTS,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> str:
    """Build in-container code that attaches framework-captured website PNGs."""
    return """
import base64 as _base64
import hashlib as _hashlib
import json as _json
from pathlib import Path as _Path

_web_root = _Path(__WORKSPACE__) / ".grading" / "website"
_web_screenshots = _web_root / "screenshots"
_web_summary_path = _web_root / "summary.json"
_web_blocks = []
_web_manifest = []
_web_total_bytes = 0
if not _web_screenshots.is_dir():
    raise RuntimeError("WEB_VISUAL_EVIDENCE_FAILED: screenshot directory is missing")
try:
    _web_summary = _json.loads(_web_summary_path.read_text(encoding="utf-8"))
except Exception as _exc:
    raise RuntimeError("WEB_VISUAL_EVIDENCE_FAILED: invalid summary.json: " + str(_exc))
_web_declared = []
for _item in _web_summary.get("screenshots", []):
    _relative = _item.get("path", "") if isinstance(_item, dict) else ""
    _candidate = (_web_root / _relative).resolve()
    try:
        _candidate.relative_to(_web_root.resolve())
    except ValueError:
        continue
    if _candidate.is_file() and _candidate.suffix.lower() == ".png":
        _web_declared.append(_candidate)
for _index, _png in enumerate(_web_declared, 1):
    if len(_web_manifest) >= __MAX_SCREENSHOTS__:
        break
    _data = _png.read_bytes()
    if not _data or _web_total_bytes + len(_data) > __MAX_IMAGE_BYTES__:
        continue
    _web_total_bytes += len(_data)
    _web_blocks.append({
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64," + _base64.b64encode(_data).decode("ascii")},
    })
    _web_blocks.append({"type": "text", "text": "Website screenshot: " + _png.name})
    _web_manifest.append({
        "path": _png.relative_to(_web_root).as_posix(),
        "mime_type": "image/png",
        "sha256": _hashlib.sha256(_data).hexdigest(),
        "size_bytes": len(_data),
    })
if not _web_blocks:
    raise RuntimeError("WEB_VISUAL_EVIDENCE_FAILED: no usable PNG screenshots")
_website_evidence = {"blocks": _web_blocks, "manifest": _web_manifest}
""".replace("__WORKSPACE__", json.dumps(workspace_path)).replace(
        "__MAX_SCREENSHOTS__", str(max_screenshots)
    ).replace("__MAX_IMAGE_BYTES__", str(max_image_bytes))
