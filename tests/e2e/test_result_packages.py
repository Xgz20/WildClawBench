import errno
import os
import unittest
import zipfile
from unittest.mock import patch

from src.e2e.artifacts import freeze_metadata_files, inventory
from src.e2e.common import read_json
from src.e2e.engine import run_batch
from src.e2e.packages import export_package, import_package
from tests.e2e import test_scheduler as scheduler_fixture


class ResultPackageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scheduler_fixture.SchedulerTests()
        self.fixture.setUp()
        run_batch(self.fixture.root, self.fixture.config, driver_factory=self.fixture.factory)

    def tearDown(self):
        self.fixture.tearDown()

    def test_cleanup_failure_preserves_a_verified_export_and_receipt(self):
        output = self.fixture.root / "exports/result.zip"
        with patch("src.e2e.packages.remove_temporary_tree", side_effect=OSError(errno.ENOTEMPTY, "metadata writer")):
            receipt = export_package(self.fixture.root, output, keys=["unit/run-0001/t0"])
        self.assertEqual(read_json(output.with_suffix(".zip.json")), receipt)
        self.assertEqual(len(list(output.parent.glob("*-cleanup.json"))), 1)
        self.assertEqual(import_package(output, output.with_suffix(".zip.json"), self.fixture.root / "recipient")["status"], "imported")

    @unittest.skipIf(os.name == "nt", "macOS metadata descriptor replacement")
    def test_export_snapshot_is_stable_with_an_existing_metadata_writer(self):
        output = self.fixture.root / "exports/result.zip"
        writers = []

        def freeze(root):
            path = root / ".DS_Store"
            path.write_bytes(b"observed metadata")
            writers.append(path.open("r+b"))
            freeze_metadata_files(root)

        def capture(root, **kwargs):
            result = inventory(root, **kwargs)
            writers[0].seek(0)
            writers[0].write(b"subsequent update")
            writers[0].flush()
            return result

        try:
            with patch("src.e2e.packages.freeze_metadata_files", side_effect=freeze), patch("src.e2e.packages.inventory", side_effect=capture):
                export_package(self.fixture.root, output, keys=["unit/run-0001/t0"])
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read(".DS_Store"), b"observed metadata")
        finally:
            for writer in writers:
                writer.close()
