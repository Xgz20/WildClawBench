from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from eval_e2e.e2e_manifest import RunEntry
from eval_e2e.grade_runs import (
    DEFAULT_DOCKER_IMAGE,
    copy_gt_into_container,
    find_existing_run_dir,
    grade_one,
)


def _entry() -> RunEntry:
    return RunEntry(
        task_id="02_Code_task_001", category="02_Code",
        task_file="tasks/x.md", workspace_src="workspace/02_Code/task_001",
        project_dir="xopglm52/02_Code_task_001/tmp_workspace",
        model="xopglm52", reasoning_effort="medium",
        prompt_rewritten=True, prompt_rewrite_map={}, status="collected",
    )


TASK_MD = """---
id: 02_Code_task_001
category: 02_Code
timeout_seconds: 300
grading_type: automated
---
## Prompt

改 /tmp_workspace/project/converter.py

## Automated Checks

```python
def grade(**kwargs) -> dict:
    return {"overall_score": 1.0}
```

## Workspace Path

```
workspace/02_Code/task_001
```

## Env

```
```
"""


def _setup(tmp: str):
    root = Path(tmp)
    (root / "tasks").mkdir(parents=True)
    (root / "tasks" / "x.md").write_text(TASK_MD, encoding="utf-8")
    src = root / "workspace" / "02_Code" / "task_001"
    (src / "exec").mkdir(parents=True)
    (src / "gt").mkdir(parents=True)
    (src / "gt" / "expected.json").write_text("{}", encoding="utf-8")
    e2e_root = root / "e2e"
    proj = e2e_root / "xopglm52" / "02_Code_task_001" / "tmp_workspace"
    proj.mkdir(parents=True)
    return root, e2e_root, proj


class DefaultsTest(unittest.TestCase):
    def test_default_image_is_astroncode_v04(self) -> None:
        self.assertEqual(DEFAULT_DOCKER_IMAGE,
                         "wildclawbench-astroncode-ubuntu:v0.4")


class CopyGtTest(unittest.TestCase):
    def test_copies_gt_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ws"
            (src / "gt").mkdir(parents=True)
            with mock.patch("eval_e2e.grade_runs.subprocess.run") as run:
                run.return_value = mock.Mock(returncode=0, stderr="")
                got = copy_gt_into_container("t1", src)
            args = run.call_args[0][0]
        self.assertTrue(got)
        self.assertIn("cp", args)
        self.assertEqual(args[-1], "t1:/tmp_workspace/gt")

    def test_skips_when_gt_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "ws"
            src.mkdir()
            with mock.patch("eval_e2e.grade_runs.subprocess.run") as run:
                got = copy_gt_into_container("t1", src)
        self.assertFalse(got)
        run.assert_not_called()


class GradeOneTest(unittest.TestCase):
    def test_mounts_project_dir_and_writes_score(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, proj = _setup(tmp)
            out_root = root / "out"
            run_dir = out_root / "round-1" / "xopglm52" / "astroncode-desktop" \
                / "02_Code" / "02_Code_task_001" / "slug1"
            run_dir.mkdir(parents=True)

            def mock_run_grading(**kwargs):
                # 模拟 run_grading 写入 score.json
                score_path = kwargs["output_dir"] / "score.json"
                score_path.write_text(json.dumps({"overall_score": 0.75}), encoding="utf-8")
                return {"overall_score": 0.75}

            with mock.patch("eval_e2e.grade_runs.start_container") as start, \
                 mock.patch("eval_e2e.grade_runs.remove_container") as remove, \
                 mock.patch("eval_e2e.grade_runs.subprocess.run") as docker_cp, \
                 mock.patch("eval_e2e.grade_runs.copy_gt_into_container",
                            return_value=True), \
                 mock.patch("eval_e2e.grade_runs.run_grading",
                            side_effect=mock_run_grading) as grading:
                docker_cp.return_value = mock.Mock(returncode=0, stderr="")
                got = grade_one(_entry(), root, e2e_root, out_root,
                                DEFAULT_DOCKER_IMAGE, run_dir=run_dir)
            score = json.loads((run_dir / "score.json").read_text(encoding="utf-8"))
        self.assertEqual(got["status"], "graded")
        self.assertEqual(score["overall_score"], 0.75)
        # 项目目录被挂为容器工作区
        self.assertEqual(start.call_args.args[1], str(proj))
        self.assertEqual(start.call_args.kwargs["docker_image"], DEFAULT_DOCKER_IMAGE)
        remove.assert_called()
        # 验证 docker cp 调用：项目目录复制到容器
        docker_cp.assert_called_once()
        cp_args = docker_cp.call_args[0][0]
        self.assertIn("docker", cp_args)
        self.assertIn("cp", cp_args)
        self.assertIn(f"{proj}/.", cp_args)
        self.assertIn("02_Code_task_001:/tmp_workspace/", cp_args)
        # grade 参数由 parse_task_md 原样透传
        self.assertIn("def grade", grading.call_args.kwargs["automated_checks"])

    def test_writes_error_score_when_grading_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, _ = _setup(tmp)
            out_root = root / "out"
            run_dir = out_root / "r"
            run_dir.mkdir(parents=True)

            def mock_write_error(output_dir, task_id, message):
                # 模拟 write_error_score 写入 score.json
                score_path = output_dir / "score.json"
                score_path.write_text(json.dumps({"overall_score": 0.0, "error": message}), encoding="utf-8")
                return {"overall_score": 0.0, "error": message}

            with mock.patch("eval_e2e.grade_runs.start_container"), \
                 mock.patch("eval_e2e.grade_runs.remove_container") as remove, \
                 mock.patch("eval_e2e.grade_runs.subprocess.run") as docker_cp, \
                 mock.patch("eval_e2e.grade_runs.copy_gt_into_container",
                            return_value=True), \
                 mock.patch("eval_e2e.grade_runs.run_grading",
                            side_effect=RuntimeError("boom")), \
                 mock.patch("eval_e2e.grade_runs.write_error_score",
                            side_effect=mock_write_error):
                docker_cp.return_value = mock.Mock(returncode=0, stderr="")
                got = grade_one(_entry(), root, e2e_root, out_root,
                                DEFAULT_DOCKER_IMAGE, run_dir=run_dir)
            self.assertEqual(got["status"], "error")
            self.assertTrue((run_dir / "score.json").is_file())
            remove.assert_called()  # 异常路径也要清理容器

    def test_removes_container_even_when_start_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, e2e_root, _ = _setup(tmp)
            run_dir = root / "out" / "r"
            run_dir.mkdir(parents=True)

            def mock_write_error(output_dir, task_id, message):
                score_path = output_dir / "score.json"
                score_path.write_text(json.dumps({"overall_score": 0.0, "error": message}), encoding="utf-8")
                return {"overall_score": 0.0, "error": message}

            with mock.patch("eval_e2e.grade_runs.start_container",
                            side_effect=RuntimeError("no docker")), \
                 mock.patch("eval_e2e.grade_runs.remove_container") as remove, \
                 mock.patch("eval_e2e.grade_runs.subprocess.run") as docker_cp, \
                 mock.patch("eval_e2e.grade_runs.write_error_score",
                            side_effect=mock_write_error):
                docker_cp.return_value = mock.Mock(returncode=0, stderr="")
                got = grade_one(_entry(), root, e2e_root, root / "out",
                                DEFAULT_DOCKER_IMAGE, run_dir=run_dir)
            self.assertEqual(got["status"], "error")
            remove.assert_called()


class FindRunDirTest(unittest.TestCase):
    def test_picks_latest_slug_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "round-1" / "xopglm52" / "astroncode-desktop" \
                / "02_Code" / "02_Code_task_001"
            (base / "xopglm52_20260810_1200_aaaaaa").mkdir(parents=True)
            latest = base / "xopglm52_20260810_1634_bbbbbb"
            latest.mkdir(parents=True)
            got = find_existing_run_dir(Path(tmp), _entry())
        self.assertEqual(got, latest)

    def test_returns_none_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(find_existing_run_dir(Path(tmp), _entry()))


if __name__ == "__main__":
    unittest.main()
