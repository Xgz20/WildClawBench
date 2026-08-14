from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.agents.deepseek_harness.skills import (
    DshSkillError,
    build_dsh_prompt,
    install_dsh_skills,
    normalize_dsh_skill_name,
)


class DeepSeekHarnessSkillTests(unittest.TestCase):
    def _write_skill(
        self,
        root: Path,
        directory: str,
        *,
        name: str,
        body: str = "Run {baseDir}/scripts/run.sh",
    ) -> Path:
        bundle = root / directory
        (bundle / "references").mkdir(parents=True)
        (bundle / "scripts").mkdir()
        (bundle / "assets").mkdir()
        (bundle / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            'description: "Test skill"\n'
            "metadata:\n"
            "  owner: wcb\n"
            "---\n\n"
            f"{body}\n",
            encoding="utf-8",
        )
        (bundle / "references" / "notes.md").write_text("notes\n", encoding="utf-8")
        (bundle / "scripts" / "run.sh").write_text("echo ok\n", encoding="utf-8")
        (bundle / "assets" / "input.txt").write_text("input\n", encoding="utf-8")
        return bundle

    def test_normalize_skill_name_to_lowercase_kebab_case(self) -> None:
        self.assertEqual(normalize_dsh_skill_name("03_task2"), "03-task2")
        self.assertEqual(normalize_dsh_skill_name("Architecture"), "architecture")
        self.assertEqual(normalize_dsh_skill_name("agent-browser"), "agent-browser")

    def test_build_prompt_prepends_native_gestures_in_declared_order(self) -> None:
        self.assertEqual(
            build_dsh_prompt("Complete the task", ["03-task2", "agent-browser"]),
            "/03-task2\n/agent-browser\n\nComplete the task",
        )
        self.assertEqual(build_dsh_prompt("Complete the task", []), "Complete the task")

    def test_install_stages_complete_bundle_and_rewrites_only_staged_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            source = self._write_skill(skills_root, "03_task2", name="03_task2")
            original = (source / "SKILL.md").read_text(encoding="utf-8")
            copied_commands: list[list[str]] = []

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                if command[:2] == ["docker", "cp"]:
                    copied_commands.append(command)
                    staged = Path(command[2].removesuffix("/."))
                    staged_skill = (staged / "SKILL.md").read_text(encoding="utf-8")
                    self.assertIn("name: 03-task2", staged_skill)
                    self.assertIn(
                        "/root/.dsh/skills/03-task2/scripts/run.sh",
                        staged_skill,
                    )
                    self.assertEqual(
                        (staged / "references" / "notes.md").read_text(encoding="utf-8"),
                        "notes\n",
                    )
                    self.assertEqual(
                        (staged / "scripts" / "run.sh").read_text(encoding="utf-8"),
                        "echo ok\n",
                    )
                    self.assertEqual(
                        (staged / "assets" / "input.txt").read_text(encoding="utf-8"),
                        "input\n",
                    )
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.deepseek_harness.skills.subprocess.run",
                side_effect=fake_run,
            ):
                names = install_dsh_skills(
                    "dsh-task",
                    "03_task2\n",
                    str(skills_root),
                )

            self.assertEqual(names, ["03-task2"])
            self.assertEqual(len(copied_commands), 1)
            self.assertEqual(
                copied_commands[0][3],
                "dsh-task:/root/.dsh/skills/03-task2/",
            )
            self.assertEqual((source / "SKILL.md").read_text(encoding="utf-8"), original)

    def test_install_rejects_normalized_name_collisions_before_docker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            self._write_skill(skills_root, "first", name="Foo_bar")
            self._write_skill(skills_root, "second", name="foo-bar")

            with patch("src.agents.deepseek_harness.skills.subprocess.run") as run_mock:
                with self.assertRaisesRegex(
                    DshSkillError,
                    "normalized skill name collision.*foo-bar",
                ):
                    install_dsh_skills(
                        "dsh-task",
                        "first\nsecond\n",
                        str(skills_root),
                    )

            run_mock.assert_not_called()

    def test_install_rejects_symlinked_skill_file_without_modifying_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            skills_root = root / "skills"
            bundle = skills_root / "linked"
            bundle.mkdir(parents=True)
            target = root / "shared-skill.md"
            original = (
                "---\n"
                "name: linked_skill\n"
                "description: Linked skill\n"
                "---\n\n"
                "Keep this source unchanged.\n"
            )
            target.write_text(original, encoding="utf-8")
            (bundle / "SKILL.md").symlink_to(target)
            caught: DshSkillError | None = None

            with patch(
                "src.agents.deepseek_harness.skills.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ) as run_mock:
                try:
                    install_dsh_skills("dsh-task", "linked\n", str(skills_root))
                except DshSkillError as exc:
                    caught = exc

            self.assertEqual(target.read_text(encoding="utf-8"), original)
            self.assertIsNotNone(caught)
            self.assertRegex(str(caught), "SKILL.md must not be a symlink")
            run_mock.assert_not_called()

    def test_install_preserves_yaml_12_scalars_and_frontmatter_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "yaml_12"
            bundle.mkdir(parents=True)
            source = (
                "---\n"
                "name: yaml_12\n"
                "description: on\n"
                "metadata:\n"
                "  enabled: yes\n"
                "  mode: on\n"
                "---\n\n"
                "Run {baseDir}/scripts/run.sh\n"
            )
            (bundle / "SKILL.md").write_text(source, encoding="utf-8")
            staged_text = ""

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                nonlocal staged_text
                if command[:2] == ["docker", "cp"]:
                    staged = Path(command[2].removesuffix("/."))
                    staged_text = (staged / "SKILL.md").read_text(encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.deepseek_harness.skills.subprocess.run",
                side_effect=fake_run,
            ):
                names = install_dsh_skills(
                    "dsh-task",
                    "yaml_12\n",
                    str(skills_root),
                )

            self.assertEqual(names, ["yaml-12"])
            self.assertEqual(
                staged_text,
                source.replace("name: yaml_12", "name: yaml-12").replace(
                    "{baseDir}",
                    "/root/.dsh/skills/yaml-12",
                ),
            )
            self.assertEqual((bundle / "SKILL.md").read_text(encoding="utf-8"), source)


if __name__ == "__main__":
    unittest.main()
