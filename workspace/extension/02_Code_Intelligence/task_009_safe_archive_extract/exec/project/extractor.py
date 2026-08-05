"""Plugin bundle extraction.

This starter implementation preserves the public API but is intentionally
incomplete. Harden ``extract_plugin`` without changing its signature.
"""

from pathlib import Path
import zipfile


class ExtractionError(ValueError):
    """Raised when a plugin bundle cannot be installed safely."""


def extract_plugin(
    archive_path,
    install_dir,
    *,
    max_entries=128,
    max_uncompressed_bytes=8 * 1024 * 1024,
):
    """Extract a valid ZIP into a new install directory.

    ``install_dir`` must not already exist. Return the sorted POSIX-style
    relative paths of extracted regular files. Unsafe or malformed bundles
    must raise ``ExtractionError``.
    """
    archive_path = Path(archive_path)
    install_dir = Path(install_dir)

    try:
        with zipfile.ZipFile(archive_path) as bundle:
            members = bundle.infolist()
            if len(members) > max_entries:
                raise ExtractionError("bundle has too many entries")
            if sum(member.file_size for member in members) > max_uncompressed_bytes:
                raise ExtractionError("bundle is too large")

            install_dir.mkdir(parents=True)
            bundle.extractall(install_dir)
            return sorted(
                member.filename
                for member in members
                if not member.is_dir()
            )
    except zipfile.BadZipFile as exc:
        raise ExtractionError("invalid ZIP bundle") from exc
