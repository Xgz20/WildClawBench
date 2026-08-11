from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from eval_e2e.e2e_manifest import Manifest, RunEntry
from eval_e2e.prepare_workspaces import (
    copy_exec_dir,
    prepare_one,
    read_task_list,
    render_checklist,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_src(root: Path) -> Path:
    """造一个含 exec/ 与 gt/ 的源工作区。"""
    src = root / "workspace" / "02_Code" / "task_001"
    (src / "exec" / "project").mkdir(parents=True)
    (src / "exec" / "project" / "converter.py").write_text("x = 1\n", encoding="utf-8")
    (src / "gt").mkdir(parents=True)
    (src / "gt" / "expected.json").write_text('{"a": 1}\n', encoding="utf-8")
    return src


def _entry(project_dir: str) -> RunEntry:
    return RunEntry(
        task_id="02_Code_task_001", category="02_Code",
        task_file="tasks/x.md", workspace_src="workspace/02_Code/task_001",
        project_dir=project_dir, model="xopglm52", reasoning_effort="medium",
        prompt_rewritten=True, prompt_rewrite_map={}, status="pending",
    )


class CopyExecDirTest(unittest.TestCase):
    def test_copies_exec_contents_to_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = _make_src(root)
            proj = root / "out" / "task_001" / "tmp_workspace"
            copy_exec_dir(src, proj)
            self.assertTrue((proj / "project" / "converter.py").is_file())

    def test_never_copies_gt_directory(self) -> None:
        """GT 隔离回归断言：项目目录内不得出现 gt/ 或其内容。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = _make_src(root)
            proj = root / "out" / "task_001" / "tmp_workspace"
            copy_exec_dir(src, proj)
            leaked = [str(p.relative_to(proj)) for p in proj.rglob("*")
                      if "gt" in p.parts or p.name == "expected.json"]
        self.assertEqual(leaked, [])

    def test_creates_empty_dir_when_exec_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "empty_src"
            src.mkdir()
            proj = root / "out" / "tmp_workspace"
            copy_exec_dir(src, proj)
            self.assertTrue(proj.is_dir())


class PrepareOneTest(unittest.TestCase):
    def test_writes_both_prompt_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_src(root)
            e2e_root = root / "out"
            entry = _entry("xopglm52/02_Code_task_001/tmp_workspace")
            prepare_one(entry, root, e2e_root,
                        "改 /tmp_workspace/project/converter.py")
            case_dir = e2e_root / "xopglm52" / "02_Code_task_001"
            original = (case_dir / "prompt_original.txt").read_text(encoding="utf-8")
            desktop = (case_dir / "prompt_desktop.txt").read_text(encoding="utf-8")
        self.assertIn("/tmp_workspace/project/converter.py", original)
        self.assertNotIn("改 /tmp_workspace/project", desktop)
        self.assertIn(str(case_dir / "tmp_workspace" / "project" / "converter.py"),
                      desktop)

    def test_records_rewrite_map_on_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_src(root)
            e2e_root = root / "out"
            entry = _entry("xopglm52/02_Code_task_001/tmp_workspace")
            prepare_one(entry, root, e2e_root, "见 /tmp_workspace/a.txt")
        self.assertTrue(entry.prompt_rewritten)
        self.assertEqual(
            entry.prompt_rewrite_map["/tmp_workspace"],
            str(e2e_root / "xopglm52" / "02_Code_task_001" / "tmp_workspace"),
        )

    def test_project_dir_tail_is_tmp_workspace(self) -> None:
        """尾部命名对齐 CLI 侧，Prompt 只需替换前缀。"""
        entry = _entry("xopglm52/02_Code_task_001/tmp_workspace")
        self.assertEqual(Path(entry.project_dir).name, "tmp_workspace")


class ReadTaskListTest(unittest.TestCase):
    def test_skips_blank_lines_and_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "list.txt"
            p.write_text(
                "# 注释\n\ntasks/a.md\n  tasks/b.md  \n# 又一个注释\n",
                encoding="utf-8",
            )
            got = read_task_list(p)
        self.assertEqual(got, ["tasks/a.md", "tasks/b.md"])


class RenderChecklistTest(unittest.TestCase):
    def test_checklist_contains_abs_path_model_and_prompt_ref(self) -> None:
        manifest = Manifest(
            e2e_root="out", created_at="2026-08-10T12:00:00+08:00",
            runs=[_entry("xopglm52/02_Code_task_001/tmp_workspace")],
        )
        got = render_checklist(manifest, Path("/data1/out"))
        self.assertIn("/data1/out/xopglm52/02_Code_task_001/tmp_workspace", got)
        self.assertIn("xopglm52", got)
        self.assertIn("medium", got)
        self.assertIn("prompt_desktop.txt", got)
        self.assertIn("- [ ]", got)


class RealWorkspaceContractTest(unittest.TestCase):
    def test_repo_workspaces_use_exec_gt_layout(self) -> None:
        """回归：仓库工作区应维持 exec/ + gt/ 分离约定。"""
        gt_dirs = list(REPO_ROOT.glob("workspace/**/gt"))
        self.assertTrue(gt_dirs, "未找到任何 gt 目录，exec/gt 约定可能已变更")
        for gt in gt_dirs[:5]:
            self.assertTrue((gt.parent / "exec").is_dir(),
                            f"{gt.parent} 有 gt/ 但缺 exec/")


if __name__ == "__main__":
    unittest.main()
