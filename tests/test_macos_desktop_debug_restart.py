from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    REPO_ROOT
    / "tools/report/e2e-shared/desktop-debug/restart_macos_desktop_debug.sh"
)
WEB_COPY = (
    REPO_ROOT
    / "tools/report/skills/web-e2e/run-web-e2e/scripts/"
    "restart_macos_desktop_debug.sh"
)


class ManagedMacOSDesktopRestartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="macos-desktop-restart-")
        self.root = Path(self.temp_dir.name)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.app = self.root / "Codex.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        (self.app / "Contents/Info.plist").write_text("fixture\n", encoding="utf-8")
        self.listener = self.root / "listener.ready"
        self.app_running = self.root / "app.running"
        self.launchctl_log = self.root / "launchctl.log"
        self.open_log = self.root / "open.log"
        self.quit_log = self.root / "quit.log"
        self.pkill_log = self.root / "pkill.log"
        self.nohup_log = self.root / "nohup.log"
        self.status_root = self.root / "status"
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.root / "home"),
                "FAKE_APP_PATH": str(self.app),
                "FAKE_LISTENER_FILE": str(self.listener),
                "FAKE_APP_RUNNING_FILE": str(self.app_running),
                "FAKE_LAUNCHCTL_LOG": str(self.launchctl_log),
                "FAKE_OPEN_LOG": str(self.open_log),
                "FAKE_QUIT_LOG": str(self.quit_log),
                "FAKE_PKILL_LOG": str(self.pkill_log),
                "FAKE_NOHUP_LOG": str(self.nohup_log),
                "WCB_MACOS_UNAME_BIN": self._fake("uname", 'printf "Darwin\\n"'),
                "WCB_MACOS_ID_BIN": self._fake("id", 'printf "501\\n"'),
                "WCB_MACOS_UUIDGEN_BIN": self._fake(
                    "uuidgen", 'printf "00000000-0000-4000-8000-000000000001\\n"'
                ),
                "WCB_MACOS_PLUTIL_BIN": self._fake(
                    "plutil", 'printf "com.openai.codex\\n"'
                ),
                "WCB_MACOS_LAUNCHCTL_BIN": self._fake(
                    "launchctl",
                    """
printf '%s\\n' "$*" >> "$FAKE_LAUNCHCTL_LOG"
if [[ "$1" == "print" ]]; then
  [[ -n "${FAKE_EXISTING_LABEL:-}" && "$2" == *"$FAKE_EXISTING_LABEL" ]]
  exit $?
fi
if [[ "$1" == "bootstrap" && "${FAKE_BOOTSTRAP_FAIL:-0}" == "1" ]]; then
  exit 17
fi
exit 0
""",
                ),
                "WCB_MACOS_LSOF_BIN": self._fake(
                    "lsof",
                    '[[ -f "$FAKE_LISTENER_FILE" ]] || exit 1\nprintf "4242\\n"',
                ),
                "WCB_MACOS_PS_BIN": self._fake(
                    "ps", 'printf "%s\\n" "$FAKE_APP_PATH/Contents/MacOS/Codex"'
                ),
                "WCB_MACOS_PGREP_BIN": self._fake(
                    "pgrep", '[[ -f "$FAKE_APP_RUNNING_FILE" ]]'
                ),
                "WCB_MACOS_PKILL_BIN": self._fake(
                    "pkill",
                    """
printf '%s\\n' "$*" >> "$FAKE_PKILL_LOG"
if [[ "$*" == *"-TERM"* ]]; then
  /bin/rm -f -- "$FAKE_APP_RUNNING_FILE"
fi
""",
                ),
                "WCB_MACOS_OSASCRIPT_BIN": self._fake(
                    "osascript",
                    """
printf '%s\\n' "$*" >> "$FAKE_QUIT_LOG"
if [[ "$1" == "-e" ]]; then
  if [[ "${FAKE_QUIT_REQUIRES_CONFIRM:-0}" != "1" ]]; then
    /bin/rm -f -- "$FAKE_APP_RUNNING_FILE"
  fi
elif [[ "${FAKE_CONFIRM_MATCH:-0}" == "1" ]]; then
  printf 'CONFIRMED\\n'
  /bin/rm -f -- "$FAKE_APP_RUNNING_FILE"
else
  printf 'NO_MATCH\\n'
fi
""",
                ),
                "WCB_MACOS_OPEN_BIN": self._fake(
                    "open",
                    """
printf '%s\\n' "$*" >> "$FAKE_OPEN_LOG"
: > "$FAKE_LISTENER_FILE"
""",
                ),
                "WCB_MACOS_CURL_BIN": self._fake(
                    "curl",
                    """
[[ -f "$FAKE_LISTENER_FILE" ]] || exit 7
url="${!#}"
if [[ "$url" == */json/version ]]; then
  printf '{"webSocketDebuggerUrl":"ws://127.0.0.1/devtools/browser/test"}\\n'
else
  printf '[{"type":"page","webSocketDebuggerUrl":"ws://127.0.0.1/devtools/page/test"}]\\n'
fi
""",
                ),
                "WCB_MACOS_SLEEP_BIN": self._fake("sleep", "exit 0"),
                "WCB_MACOS_NOHUP_BIN": self._fake(
                    "nohup", 'printf "%s\\n" "$*" >> "$FAKE_NOHUP_LOG"'
                ),
            }
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _fake(self, name: str, body: str) -> str:
        path = self.bin_dir / name
        path.write_text(f"#!/bin/bash\nset -euo pipefail\n{body}\n", encoding="utf-8")
        path.chmod(0o755)
        return str(path)

    def _run(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", str(SCRIPT), *args],
            cwd=REPO_ROOT,
            env=env or self.env,
            check=False,
            capture_output=True,
            text=True,
        )

    def _read_eventually(self, path: Path) -> str:
        for _ in range(100):
            if path.is_file():
                return path.read_text(encoding="utf-8")
            time.sleep(0.01)
        self.fail(f"timed out waiting for simulated event log: {path}")

    def test_source_is_one_shot_and_web_copy_matches(self) -> None:
        source = SCRIPT.read_bytes()
        self.assertNotIn(b"launchctl submit", source)
        self.assertIn(b"<key>RunAtLoad</key>", source)
        self.assertIn(b"<key>KeepAlive</key>", source)
        self.assertIn("退出 Codex？".encode(), source)
        self.assertIn(b'elementRole is "AXButton"', source)
        self.assertEqual(WEB_COPY.read_bytes(), source)
        help_result = self._run("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("KeepAlive=false", help_result.stdout)

    def test_schedule_writes_scheduled_status_and_one_shot_plist(self) -> None:
        result = self._run(
            "--app-path",
            str(self.app),
            "--status-root",
            str(self.status_root),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        runs = list(self.status_root.iterdir())
        self.assertEqual(len(runs), 1)
        status = json.loads((runs[0] / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "SCHEDULED")
        plist = (runs[0] / "job.plist").read_text(encoding="utf-8")
        self.assertIn("<key>RunAtLoad</key>\n  <true/>", plist)
        self.assertIn("<key>KeepAlive</key>\n  <false/>", plist)
        self.assertNotIn("KeepAlive</key>\n  <true/>", plist)
        self.assertIn("bootstrap gui/501", self.launchctl_log.read_text(encoding="utf-8"))

    def test_worker_starts_once_passes_and_cleanup_boots_out(self) -> None:
        self.app_running.write_text("running\n", encoding="utf-8")
        state_dir = self.root / "worker-state"
        state_dir.mkdir()
        plist = state_dir / "job.plist"
        plist.write_text("fixture\n", encoding="utf-8")
        result = self._run(
            "--worker",
            "--job-label",
            "com.wildclawbench.desktop-debug-restart.codex",
            "--job-uid",
            "501",
            "--state-dir",
            str(state_dir),
            "--plist-path",
            str(plist),
            "--run-id",
            "fixture-run",
            "--created-at",
            "2026-09-18T00:00:00Z",
            "--app-path",
            str(self.app),
            "--port",
            "9230",
            "--delay-seconds",
            "0",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads((state_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "PASSED")
        self.assertEqual(len(self.open_log.read_text(encoding="utf-8").splitlines()), 1)
        self.assertEqual(len(self.quit_log.read_text(encoding="utf-8").splitlines()), 1)
        self.assertIn("--cleanup-worker", self._read_eventually(self.nohup_log))

        cleanup = self._run(
            "--cleanup-worker",
            "--job-label",
            "com.wildclawbench.desktop-debug-restart.codex",
            "--job-uid",
            "501",
            "--state-dir",
            str(state_dir),
            "--plist-path",
            str(plist),
            "--app-path",
            str(self.app),
        )
        self.assertEqual(cleanup.returncode, 0, cleanup.stderr)
        self.assertFalse(plist.exists())
        self.assertIn(
            "bootout gui/501/com.wildclawbench.desktop-debug-restart.codex",
            self.launchctl_log.read_text(encoding="utf-8"),
        )

    def test_worker_confirms_only_the_recognized_codex_quit_dialog(self) -> None:
        self.app_running.write_text("running\n", encoding="utf-8")
        state_dir = self.root / "confirm-worker"
        state_dir.mkdir()
        plist = state_dir / "job.plist"
        plist.write_text("fixture\n", encoding="utf-8")
        env = dict(self.env)
        env["FAKE_QUIT_REQUIRES_CONFIRM"] = "1"
        env["FAKE_CONFIRM_MATCH"] = "1"
        result = self._run(
            "--worker",
            "--job-label",
            "com.wildclawbench.desktop-debug-restart.codex",
            "--job-uid",
            "501",
            "--state-dir",
            str(state_dir),
            "--plist-path",
            str(plist),
            "--run-id",
            "confirm-run",
            "--created-at",
            "2026-09-18T00:00:00Z",
            "--app-path",
            str(self.app),
            "--port",
            "9230",
            "--delay-seconds",
            "0",
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Confirmed the recognized Codex quit dialog", result.stdout)
        invocations = self.quit_log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(invocations), 2)
        self.assertTrue(invocations[0].startswith("-e "))
        self.assertEqual(invocations[1], "- Codex")
        self.assertFalse(self.pkill_log.exists())

    def test_unknown_quit_dialog_is_not_confirmed_and_uses_term_fallback(self) -> None:
        self.app_running.write_text("running\n", encoding="utf-8")
        state_dir = self.root / "unknown-dialog-worker"
        state_dir.mkdir()
        plist = state_dir / "job.plist"
        plist.write_text("fixture\n", encoding="utf-8")
        env = dict(self.env)
        env["FAKE_QUIT_REQUIRES_CONFIRM"] = "1"
        result = self._run(
            "--worker",
            "--job-label",
            "com.wildclawbench.desktop-debug-restart.codex",
            "--job-uid",
            "501",
            "--state-dir",
            str(state_dir),
            "--plist-path",
            str(plist),
            "--run-id",
            "unknown-dialog-run",
            "--created-at",
            "2026-09-18T00:00:00Z",
            "--app-path",
            str(self.app),
            "--port",
            "9230",
            "--delay-seconds",
            "0",
            env=env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Confirmed the recognized Codex quit dialog", result.stdout)
        pkill = self.pkill_log.read_text(encoding="utf-8")
        self.assertIn("-TERM", pkill)
        self.assertNotIn("-KILL", pkill)

    def test_existing_legacy_or_current_job_fails_closed(self) -> None:
        for label in (
            "com.wildclawbench.general-e2e.codex-refresh",
            "com.wildclawbench.general-e2e.codex-debug",
            "com.wildclawbench.desktop-debug-restart.codex",
        ):
            with self.subTest(label=label):
                env = dict(self.env)
                env["FAKE_EXISTING_LABEL"] = label
                result = self._run(
                    "--app-path",
                    str(self.app),
                    "--status-root",
                    str(self.status_root / label.rsplit(".", 1)[-1]),
                    env=env,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertRegex(result.stderr.lower(), r"active|already")

    def test_worker_resolution_failure_records_failed_and_schedules_cleanup(self) -> None:
        state_dir = self.root / "failed-worker"
        state_dir.mkdir()
        plist = state_dir / "job.plist"
        plist.write_text("fixture\n", encoding="utf-8")
        result = self._run(
            "--worker",
            "--job-label",
            "com.wildclawbench.desktop-debug-restart.codex",
            "--job-uid",
            "501",
            "--state-dir",
            str(state_dir),
            "--plist-path",
            str(plist),
            "--run-id",
            "failed-run",
            "--created-at",
            "2026-09-18T00:00:00Z",
            "--app-path",
            str(self.root / "Missing.app"),
        )
        self.assertNotEqual(result.returncode, 0)
        status = json.loads((state_dir / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "FAILED")
        self.assertIn("--cleanup-worker", self._read_eventually(self.nohup_log))

    def test_bootstrap_failure_records_failed_and_removes_plist(self) -> None:
        env = dict(self.env)
        env["FAKE_BOOTSTRAP_FAIL"] = "1"
        result = self._run(
            "--app-path",
            str(self.app),
            "--status-root",
            str(self.status_root),
            env=env,
        )
        self.assertNotEqual(result.returncode, 0)
        run = next(self.status_root.iterdir())
        status = json.loads((run / "status.json").read_text(encoding="utf-8"))
        self.assertEqual(status["status"], "FAILED")
        self.assertFalse((run / "job.plist").exists())


if __name__ == "__main__":
    unittest.main()
