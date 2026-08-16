import os
import subprocess
from pathlib import Path


def test_team_skill_links_and_ignore_rules():
    root = Path(__file__).resolve().parents[3]
    for client in (".agents", ".claude"):
        for name in ("validate-eval-dataset", "audit-eval-dataset-quality"):
            link = root / client / "skills" / name
            assert link.is_symlink()
            assert os.readlink(link) == f"../../tools/report/skills/{name}"
            assert subprocess.run(["git", "check-ignore", "-q", str(link)], cwd=root).returncode != 0
    assert subprocess.run(["git", "check-ignore", "-q", ".agents/hermesagent-production-readiness"], cwd=root).returncode == 0
