"""Reassemble the controller's verification package in the scoring sandbox."""
from pathlib import Path, PurePosixPath
import hashlib
import os
import shutil
import sys
import zipfile


def unpack(root, expected_sha256):
    root = root.resolve(strict=True)
    if os.name == "nt":
        root = Path("\\\\?\\" + str(root))
    archive = root / "bundle.zip"
    parts = sorted(root.glob("parts-*/part-*"), key=lambda piece: piece.name)
    if not parts or [p.name for p in parts] != [f"part-{i:05d}" for i in range(len(parts))]:
        raise ValueError("DESKTOP_SCORING_WEB_BUNDLE_PARTS_INVALID")
    with archive.open("wb") as target:
        for part in parts:
            with part.open("rb") as source:
                shutil.copyfileobj(source, target)
    with archive.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != expected_sha256:
            raise ValueError("DESKTOP_SCORING_WEB_BUNDLE_DRIFT")
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            path = PurePosixPath(member.filename)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.filename or ":" in member.filename
                    or not path.parts or path.parts[0] not in {"unit", "verifier"}):
                raise ValueError("DESKTOP_SCORING_WEB_BUNDLE_MEMBER_INVALID")
        bundle.extractall(root / "contents")


if __name__ == "__main__":
    unpack(Path(sys.argv[1]), sys.argv[2])
