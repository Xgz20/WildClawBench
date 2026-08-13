from __future__ import annotations

import json


DEFAULT_MAX_SLIDES = 60
# Base64 expands bytes by roughly 4/3. Keep encoded images below ~24 MiB so
# prompts and response metadata still fit common 32 MiB API request limits.
DEFAULT_MAX_IMAGE_BYTES = 18 * 1024 * 1024


def build_ppt_evidence_code(
    workspace_path: str,
    audit_path: str = "/tmp_workspace/.grading/judge",
    *,
    max_slides: int = DEFAULT_MAX_SLIDES,
    max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
) -> str:
    """Return self-contained code run inside the grading container.

    It intentionally raises a tagged error when the deck cannot be rendered;
    PPT visual grading must never silently fall back to source-only evidence.
    """
    return """
import base64 as _base64
import hashlib as _hashlib
import json as _json
import shutil as _shutil
import subprocess as _subprocess
from pathlib import Path as _Path

_ppt_ws = _Path(__WORKSPACE__)
_ppt_audit = _Path(__AUDIT__) / "rendered"
_ppt_audit.mkdir(parents=True, exist_ok=True)
_ppt_results = _ppt_ws / "results"
_ppt_files = sorted(_ppt_results.rglob('*.pptx')) if _ppt_results.is_dir() else []
if not _ppt_files:
    raise RuntimeError("PPT_RENDER_FAILED: no .pptx found under workspace/results")
_soffice = _shutil.which("soffice") or _shutil.which("libreoffice")
if not _soffice:
    raise RuntimeError("PPT_RENDER_FAILED: soffice/libreoffice is unavailable")
_ppt_blocks = []
_ppt_manifest = []
_ppt_total_bytes = 0
for _deck_index, _ppt in enumerate(_ppt_files, 1):
    _deck_dir = _ppt_audit / ("deck-%03d" % _deck_index)
    _deck_dir.mkdir(parents=True, exist_ok=True)
    _pdf = _deck_dir / (_ppt.stem + ".pdf")
    if not _pdf.exists():
        _result = _subprocess.run(
            [_soffice, "--headless", "--convert-to", "pdf", "--outdir", str(_deck_dir), str(_ppt)],
            capture_output=True, text=True, timeout=180,
        )
        if _result.returncode != 0 or not _pdf.exists():
            raise RuntimeError("PPT_RENDER_FAILED: %s" % (_result.stderr or _result.stdout or _ppt))
    try:
        import fitz as _fitz
        _doc = _fitz.open(str(_pdf))
    except Exception as _exc:
        raise RuntimeError("PPT_RENDER_FAILED: PDF renderer unavailable: %s" % _exc) from _exc
    for _slide_index, _page in enumerate(_doc, 1):
        if len(_ppt_manifest) >= __MAX_SLIDES__:
            break
        _png = _deck_dir / ("slide-%03d.png" % _slide_index)
        if not _png.exists():
            _pix = _page.get_pixmap(matrix=_fitz.Matrix(1.5, 1.5), alpha=False)
            _pix.save(str(_png))
        _data = _png.read_bytes()
        if _ppt_total_bytes + len(_data) > __MAX_IMAGE_BYTES__:
            break
        _ppt_total_bytes += len(_data)
        _digest = _hashlib.sha256(_data).hexdigest()
        _ppt_blocks.append({
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64," + _base64.b64encode(_data).decode("ascii")},
        })
        _ppt_blocks.append({"type": "text", "text": "Rendered slide %d from %s" % (_slide_index, _ppt.name)})
        _ppt_manifest.append({
            "deck": _ppt.relative_to(_ppt_results).as_posix(),
            "slide": _slide_index,
            "path": _png.relative_to(_ppt_audit.parent).as_posix(),
            "mime_type": "image/png",
            "width": _page.rect.width,
            "height": _page.rect.height,
            "sha256": _digest,
        })
    _doc.close()
if not _ppt_blocks:
    raise RuntimeError("PPT_RENDER_FAILED: no slides rendered")
_ppt_evidence = {"blocks": _ppt_blocks, "manifest": _ppt_manifest}
""".replace("__WORKSPACE__", json.dumps(workspace_path)).replace("__AUDIT__", json.dumps(audit_path)).replace("__MAX_SLIDES__", str(max_slides)).replace("__MAX_IMAGE_BYTES__", str(max_image_bytes))
