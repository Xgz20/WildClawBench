from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from PIL import Image
from wildclawbench_grading_core import ImageEvidenceError, read_image_evidence


def write_image(path: Path, *, color="red", fmt=None) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), color).save(path, format=fmt)
    return path.read_bytes()


class ImageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_supported_stills_decode_and_preserve_exact_bytes(self):
        for extension in ("png", "jpg", "webp", "gif"):
            with self.subTest(extension=extension):
                path = self.root / ("source." + extension)
                data = write_image(path)
                result = read_image_evidence(path, expected_sha256=hashlib.sha256(data).hexdigest())
                self.assertEqual(base64.b64decode(result["data_base64"]), data)
                self.assertEqual(path.read_bytes(), data)
                self.assertEqual((result["width"], result["height"]), (64, 48))
                self.assertEqual(result["engine"]["name"], "Pillow")

    def test_format_mismatch_and_truncated_pixels_are_rejected(self):
        wrong = self.root / "wrong.png"
        write_image(wrong, fmt="JPEG")
        with self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_INVALID"):
            read_image_evidence(wrong)
        data = write_image(self.root / "good.png")
        wrong.write_bytes(data[:-20])
        with self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_INVALID"):
            read_image_evidence(wrong)

    def test_animation_is_not_silently_reduced_to_first_frame(self):
        path = self.root / "animated.gif"
        Image.new("RGB", (32, 32), "red").save(path, save_all=True,
            append_images=[Image.new("RGB", (32, 32), "blue")], duration=200, loop=0)
        with self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_UNSUPPORTED"):
            read_image_evidence(path)

    def test_size_pixel_and_dimension_limits_are_explicit(self):
        path = self.root / "source.png"
        write_image(path)
        for limits in ({"max_bytes": 1}, {"max_pixels": 100}, {"max_bytes": True}):
            with self.subTest(limits=limits), self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_LIMIT"):
                read_image_evidence(path, **limits)
        Image.new("RGB", (8001, 1)).save(path)
        with self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_LIMIT"):
            read_image_evidence(path)

    def test_digest_drift_and_symlinks_are_rejected(self):
        path = self.root / "source.png"
        write_image(path)
        with self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_DIGEST_MISMATCH"):
            read_image_evidence(path, expected_sha256="0" * 64)
        link = self.root / "linked.png"
        link.symlink_to(path)
        with self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_INVALID"):
            read_image_evidence(link)

    def test_missing_decoder_is_infrastructure_error(self):
        path = self.root / "source.png"
        write_image(path)
        with patch.dict(sys.modules, {"PIL": None}), self.assertRaisesRegex(ImageEvidenceError, "IMAGE_EVIDENCE_DEPENDENCY_MISSING"):
            read_image_evidence(path)

    def test_exif_orientation_is_reported_without_rotating_or_reencoding(self):
        path = self.root / "oriented.jpg"
        exif = Image.Exif(); exif[274] = 6
        Image.new("RGB", (64, 48), "green").save(path, exif=exif)
        data = path.read_bytes(); result = read_image_evidence(path)
        self.assertEqual(result["exif_orientation"], 6)
        self.assertEqual((result["width"], result["height"]), (64, 48))
        self.assertEqual(base64.b64decode(result["data_base64"]), data)


if __name__ == "__main__":
    unittest.main()
