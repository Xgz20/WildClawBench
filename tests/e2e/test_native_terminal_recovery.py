import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from src.e2e.backend import GUEST_WORKSPACE, NATIVE_ROOT
from src.e2e.common import E2EError
from src.e2e.native_recovery import validate_capsule


class RecoveryAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capsule, self.post_path = self.root / "capsule.zip", self.root / "post.json"
        self.row = {"session_id": "original-sandbox", "attempt_id": "original-exec", "native_before": {}}
        self.files = {"workspace/project/answer.txt": b"original answer", "native/rollout.jsonl": b"native"}
        self.manifest = {"schema": "astudio.original-session-readonly-recovery/v1",
            "session_id": "original-sandbox", "original_execution_attempt": "original-exec",
            "sut_prompt_repeated": False, "application_restarted": False, "quiet_observed_milliseconds": 5000,
            "files": [{"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest(),
                       "source": (GUEST_WORKSPACE + "\\" + p[len("workspace/project/"):]
                                  if p.startswith("workspace/project/") else NATIVE_ROOT + "\\" + p[len("native/"):])}
                      for p, b in self.files.items()]}
        self.cleanup = {"schema": "wildclawbench.agentcube-process-cleanup/v1", "phase": "completed",
            "success": True, "supported": True, "after": [], "quiet_observed_milliseconds": 5000,
            "workspace": GUEST_WORKSPACE, "root_pid": 12,
            "before": [{"pid": 12, "name": "AStudio.exe", "path": "C:\\Programs\\AStudio.exe", "created": "observed"}]}

    def write(self, change=None, extra=None):
        with zipfile.ZipFile(self.capsule, "w") as z:
            z.writestr("recovery-manifest.json", json.dumps(self.manifest))
            for p, b in self.files.items():
                z.writestr(p.replace("/", "\\"), b)
            if extra:
                z.writestr(extra, b"unsafe")
        self.sha = hashlib.sha256(self.capsule.read_bytes()).hexdigest()
        post = {"schema": "astudio.original-session-post-task-cleanup/v1",
            "session_id": "original-sandbox", "original_execution_attempt": "original-exec",
            "original_archive_sha256": self.sha, "sut_prompt_repeated": False, "cleanup": self.cleanup,
            "files": [{k: f[k] for k in ("path", "size", "sha256")} for f in self.manifest["files"]]}
        if change:
            change(post)
        self.post_path.write_text(json.dumps(post))

    def verify(self):
        return validate_capsule(self.capsule, self.post_path, expected_sha256=self.sha, row=self.row)

    def test_original_windows_archive_and_post_snapshot_match(self):
        self.write()
        self.assertEqual(len(self.verify()[2]), 2)

    def test_post_cleanup_drift_rejected(self):
        self.write(lambda p: p["files"][0].update(sha256="0" * 64))
        with self.assertRaisesRegex(E2EError, "ORIGINAL_FILE_DRIFT"):
            self.verify()

    def test_other_attempt_cannot_be_reused(self):
        self.write(lambda p: p.update(original_execution_attempt="other-exec"))
        with self.assertRaisesRegex(E2EError, "IDENTITY_MISMATCH"):
            self.verify()

    def test_live_or_unquiet_process_tree_cannot_be_admitted(self):
        self.cleanup["after"] = [{"pid": 13}]
        self.write()
        with self.assertRaisesRegex(E2EError, "CLEANUP_UNVERIFIED"):
            self.verify()

    def test_resending_or_restart_is_not_original_recovery(self):
        self.manifest["application_restarted"] = True
        self.write()
        with self.assertRaisesRegex(E2EError, "MANIFEST_INVALID"):
            self.verify()

    def test_archive_path_traversal_rejected(self):
        self.write(extra="..\\escape.txt")
        with self.assertRaises(E2EError):
            self.verify()

    def test_unchanged_predispatch_native_is_not_task_evidence(self):
        f = self.manifest["files"][1]
        self.row["native_before"] = {f["source"]: {"Sha256": f["sha256"]}}
        self.write()
        with self.assertRaisesRegex(E2EError, "NOT_CHANGED_SINCE_DISPATCH"):
            self.verify()
