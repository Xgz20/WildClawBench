from __future__ import annotations

import unittest
from pathlib import Path

from eval_e2e.prompt_rewrite import CONTAINER_WORKSPACE, rewrite_prompt

PROJECT = Path("/Users/x/eval_out_e2e/m/task_001/tmp_workspace")


class PromptRewriteTest(unittest.TestCase):
    def test_container_workspace_constant(self) -> None:
        self.assertEqual(CONTAINER_WORKSPACE, "/tmp_workspace")

    def test_rewrites_prefix_and_keeps_tail_structure(self) -> None:
        out, mapping = rewrite_prompt(
            "修复 /tmp_workspace/project/converter.py 中的缺陷", PROJECT
        )
        self.assertEqual(
            out,
            f"修复 {PROJECT}/project/converter.py 中的缺陷",
        )
        self.assertEqual(mapping, {"/tmp_workspace": str(PROJECT)})

    def test_rewrites_every_occurrence(self) -> None:
        out, _ = rewrite_prompt(
            "读 /tmp_workspace/input/a.png 写 /tmp_workspace/results/r.md", PROJECT
        )
        # 两处容器路径都应被改写为项目目录前缀（尾部结构保持不变）。
        # 注意：PROJECT 尾部本身命名 tmp_workspace，改写后 out 必然仍含子串
        # "/tmp_workspace/"，故不能用 assertNotIn 判断；改判前缀出现次数。
        self.assertEqual(out.count(f"{PROJECT}/"), 2)
        self.assertIn(f"{PROJECT}/input/a.png", out)
        self.assertIn(f"{PROJECT}/results/r.md", out)

    def test_rewrites_bare_path_without_trailing_slash(self) -> None:
        out, _ = rewrite_prompt("产物放到 /tmp_workspace 下", PROJECT)
        self.assertEqual(out, f"产物放到 {PROJECT} 下")

    def test_does_not_touch_similar_but_different_prefix(self) -> None:
        """/tmp_workspace_backup 不是工作区路径，不应被改写。"""
        out, _ = rewrite_prompt("备份在 /tmp_workspace_backup/x", PROJECT)
        self.assertEqual(out, "备份在 /tmp_workspace_backup/x")

    def test_returns_empty_map_when_no_match(self) -> None:
        out, mapping = rewrite_prompt("没有任何工作区路径", PROJECT)
        self.assertEqual(out, "没有任何工作区路径")
        self.assertEqual(mapping, {})


if __name__ == "__main__":
    unittest.main()
