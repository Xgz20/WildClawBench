"""Read frozen raster evidence without OCR, resizing, re-encoding or network access."""
from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from pathlib import Path
import warnings

IMAGE_EVIDENCE_SCHEMA = "wildclawbench.image-evidence/v1"
IMAGE_SUFFIXES = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".gif": "GIF"}
IMAGE_MIMES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
MAX_IMAGE_BYTES = 5_000_000
MAX_IMAGE_PIXELS = 16_000_000


class ImageEvidenceError(ValueError):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


def is_image_evidence_format(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_SUFFIXES


def read_image_evidence(
    path: str | Path, *, expected_sha256: str | None = None,
    max_bytes: int = MAX_IMAGE_BYTES, max_pixels: int = MAX_IMAGE_PIXELS,
) -> dict:
    """Fully decode one still image and preserve the exact original byte payload.

    Pillow is needed only in the scoring CLI interpreter, never imported at core
    initialization. This checks readability, not image meaning or model vision.
    Dimensions describe stored pixels; EXIF orientation is reported, not applied.
    """
    path = Path(path)
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_IMAGE_BYTES:
        raise ImageEvidenceError("IMAGE_EVIDENCE_LIMIT", "invalid byte limit")
    if type(max_pixels) is not int or not 1 <= max_pixels <= MAX_IMAGE_PIXELS:
        raise ImageEvidenceError("IMAGE_EVIDENCE_LIMIT", "invalid pixel limit")
    if not is_image_evidence_format(path):
        raise ImageEvidenceError("IMAGE_EVIDENCE_UNSUPPORTED", "unsupported raster extension")
    if path.is_symlink() or not path.is_file():
        raise ImageEvidenceError("IMAGE_EVIDENCE_INVALID", "image must be a regular file")
    if path.stat().st_size > max_bytes:
        raise ImageEvidenceError("IMAGE_EVIDENCE_LIMIT", "image byte limit exceeded")
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ImageEvidenceError("IMAGE_EVIDENCE_LIMIT", "image grew beyond byte limit")
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ImageEvidenceError("IMAGE_EVIDENCE_DIGEST_MISMATCH", "frozen image bytes changed")
    try:
        import PIL
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:
        raise ImageEvidenceError("IMAGE_EVIDENCE_DEPENDENCY_MISSING", "Pillow is required in the scoring CLI interpreter") from exc
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as opened:
                fmt, dimensions = opened.format, opened.size
                if fmt != IMAGE_SUFFIXES[path.suffix.lower()]:
                    raise ImageEvidenceError("IMAGE_EVIDENCE_INVALID", "image format does not match extension")
                if min(dimensions) < 1 or max(dimensions) > 8000 or dimensions[0] * dimensions[1] > max_pixels:
                    raise ImageEvidenceError("IMAGE_EVIDENCE_LIMIT", "image pixel limit exceeded")
                if getattr(opened, "n_frames", 1) != 1:
                    raise ImageEvidenceError("IMAGE_EVIDENCE_UNSUPPORTED", "animated or multi-frame images require a separate contract")
                opened.verify()
            # verify checks container integrity; load also rejects truncated pixel streams.
            with Image.open(BytesIO(data)) as opened:
                opened.load()
                orientation = opened.getexif().get(274, 1)
                if type(orientation) is not int or orientation not in range(1, 9):
                    orientation = None
                mode = opened.mode
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        if isinstance(exc, ImageEvidenceError):
            raise
        raise ImageEvidenceError("IMAGE_EVIDENCE_INVALID", "image is not fully decodable") from exc
    return {
        "schema_version": IMAGE_EVIDENCE_SCHEMA,
        "source_sha256": digest,
        "source_bytes": len(data),
        "format": fmt,
        "mime_type": IMAGE_MIMES[fmt],
        "width": dimensions[0], "height": dimensions[1],
        "mode": mode, "exif_orientation": orientation,
        "engine": {"name": "Pillow", "version": PIL.__version__},
        "data_base64": base64.b64encode(data).decode("ascii"),
        "limitations": [
            "Original bytes only; no OCR, resize, crop, rotation or re-encoding.",
            "Stored-pixel coordinates; provider/model may apply its own orientation and resizing.",
            "Successful byte delivery does not prove the model perceived or interpreted the image correctly.",
        ],
    }
