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

    def test_install_rewrites_anchor_value_without_breaking_alias(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "anchored"
            bundle.mkdir(parents=True)
            source = (
                "---\n"
                "name: &skill anchored_name\n"
                "description: *skill\n"
                "---\n\n"
                "Use {baseDir}.\n"
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
                names = install_dsh_skills("dsh-task", "anchored\n", str(skills_root))

            self.assertEqual(names, ["anchored-name"])
            self.assertIn("name: &skill anchored-name", staged_text)
            self.assertIn("description: *skill", staged_text)
            self.assertEqual((bundle / "SKILL.md").read_text(encoding="utf-8"), source)

    def test_install_rewrites_alias_name_without_modifying_anchor_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "alias_name"
            bundle.mkdir(parents=True)
            source = (
                "---\n"
                "shared: &skill alias_name\n"
                "name: *skill\n"
                "description: Alias skill\n"
                "---\n\n"
                "Use {baseDir}.\n"
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
                names = install_dsh_skills("dsh-task", "alias_name\n", str(skills_root))

            self.assertEqual(names, ["alias-name"])
            self.assertIn("shared: &skill alias_name", staged_text)
            self.assertIn("name: alias-name", staged_text)
            self.assertNotIn("name: *skill", staged_text)
            self.assertEqual((bundle / "SKILL.md").read_text(encoding="utf-8"), source)

    def test_install_rewrites_block_scalar_name_without_joining_next_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "block"
            bundle.mkdir(parents=True)
            source = (
                "---\n"
                "name: |\n"
                "  block_name\n"
                "description: d\n"
                "---\n\n"
                "Use {baseDir}.\n"
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
                names = install_dsh_skills("dsh-task", "block\n", str(skills_root))

            self.assertEqual(names, ["block-name"])
            self.assertIn("name: block-name\ndescription: d", staged_text)

    def test_install_rewrites_crlf_block_scalar_name_without_losing_line_ending(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "crlf-block"
            bundle.mkdir(parents=True)
            source = (
                "---\r\n"
                "name: |\r\n"
                "  crlf_name\r\n"
                "description: d\r\n"
                "---\r\n\r\n"
                "Use {baseDir}.\r\n"
            )
            (bundle / "SKILL.md").write_bytes(source.encode("utf-8"))
            staged_text = ""

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                nonlocal staged_text
                if command[:2] == ["docker", "cp"]:
                    staged = Path(command[2].removesuffix("/."))
                    staged_text = (staged / "SKILL.md").read_bytes().decode("utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch(
                "src.agents.deepseek_harness.skills.subprocess.run",
                side_effect=fake_run,
            ):
                names = install_dsh_skills("dsh-task", "crlf-block\n", str(skills_root))

            self.assertEqual(names, ["crlf-name"])
            self.assertEqual(
                staged_text,
                source.replace(
                    "name: |\r\n  crlf_name\r\n",
                    "name: crlf-name\r\n",
                ).replace(
                    "{baseDir}", "/root/.dsh/skills/crlf-name"
                ),
            )
            self.assertEqual(
                (bundle / "SKILL.md").read_bytes().decode("utf-8"),
                source,
            )

    def test_install_rewrites_tagged_name_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "tagged-key"
            bundle.mkdir(parents=True)
            (bundle / "SKILL.md").write_text(
                "---\n!!str name: tagged_key\ndescription: d\n---\n\nBody\n",
                encoding="utf-8",
            )

            with patch(
                "src.agents.deepseek_harness.skills.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ):
                names = install_dsh_skills("dsh-task", "tagged-key\n", str(skills_root))

            self.assertEqual(names, ["tagged-key"])

    def test_install_rewrites_anchored_name_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "anchored-key"
            bundle.mkdir(parents=True)
            (bundle / "SKILL.md").write_text(
                "---\n&key name: anchored_key\ndescription: d\n---\n\nBody\n",
                encoding="utf-8",
            )

            with patch(
                "src.agents.deepseek_harness.skills.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ):
                names = install_dsh_skills("dsh-task", "anchored-key\n", str(skills_root))

            self.assertEqual(names, ["anchored-key"])

    def test_install_rejects_numeric_name_as_non_string(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "numeric"
            bundle.mkdir(parents=True)
            (bundle / "SKILL.md").write_text(
                "---\nname: 123\ndescription: Test skill\n---\n\nBody\n",
                encoding="utf-8",
            )

            with patch("src.agents.deepseek_harness.skills.subprocess.run") as run_mock:
                with self.assertRaisesRegex(DshSkillError, "requires a string name"):
                    install_dsh_skills("dsh-task", "numeric\n", str(skills_root))

            run_mock.assert_not_called()

    def test_install_rejects_boolean_description_as_non_string(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "boolean-description"
            bundle.mkdir(parents=True)
            (bundle / "SKILL.md").write_text(
                "---\nname: boolean-description\ndescription: false\n---\n\nBody\n",
                encoding="utf-8",
            )

            with patch("src.agents.deepseek_harness.skills.subprocess.run") as run_mock:
                with self.assertRaisesRegex(DshSkillError, "requires a string description"):
                    install_dsh_skills(
                        "dsh-task",
                        "boolean-description\n",
                        str(skills_root),
                    )

            run_mock.assert_not_called()

    def test_install_matches_dsh_yaml12_date_and_numeric_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            date_bundle = skills_root / "date"
            date_bundle.mkdir(parents=True)
            (date_bundle / "SKILL.md").write_text(
                "---\nname: 2020-01-01\ndescription: d\n---\n\nBody\n",
                encoding="utf-8",
            )
            numeric_bundle = skills_root / "numeric"
            numeric_bundle.mkdir(parents=True)
            (numeric_bundle / "SKILL.md").write_text(
                "---\nname: 0o123\ndescription: d\n---\n\nBody\n",
                encoding="utf-8",
            )
            exponent_bundle = skills_root / "exponent"
            exponent_bundle.mkdir(parents=True)
            (exponent_bundle / "SKILL.md").write_text(
                "---\nname: exponent\ndescription: 1e3\n---\n\nBody\n",
                encoding="utf-8",
            )
            underscored_bundle = skills_root / "underscored"
            underscored_bundle.mkdir(parents=True)
            (underscored_bundle / "SKILL.md").write_text(
                "---\nname: 1_000\ndescription: d\n---\n\nBody\n",
                encoding="utf-8",
            )
            binary_bundle = skills_root / "binary"
            binary_bundle.mkdir(parents=True)
            (binary_bundle / "SKILL.md").write_text(
                "---\nname: 0b1010\ndescription: d\n---\n\nBody\n",
                encoding="utf-8",
            )

            with patch(
                "src.agents.deepseek_harness.skills.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "", ""),
            ):
                self.assertEqual(
                    install_dsh_skills("dsh-task", "date\n", str(skills_root)),
                    ["2020-01-01"],
                )
                with self.assertRaisesRegex(DshSkillError, "requires a string name"):
                    install_dsh_skills("dsh-task", "numeric\n", str(skills_root))
                with self.assertRaisesRegex(DshSkillError, "requires a string description"):
                    install_dsh_skills("dsh-task", "exponent\n", str(skills_root))
                self.assertEqual(
                    install_dsh_skills("dsh-task", "underscored\n", str(skills_root)),
                    ["1-000"],
                )
                self.assertEqual(
                    install_dsh_skills("dsh-task", "binary\n", str(skills_root)),
                    ["0b1010"],
                )

    def test_install_rejects_duplicate_frontmatter_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            bundle = skills_root / "duplicate"
            bundle.mkdir(parents=True)
            (bundle / "SKILL.md").write_text(
                "---\nname: first\nname: second\ndescription: d\n---\n\nBody\n",
                encoding="utf-8",
            )

            with patch("src.agents.deepseek_harness.skills.subprocess.run") as run_mock:
                with self.assertRaisesRegex(DshSkillError, "duplicate YAML mapping key"):
                    install_dsh_skills("dsh-task", "duplicate\n", str(skills_root))

            run_mock.assert_not_called()

    def test_install_rejects_keys_equal_after_yaml12_scalar_resolution(self) -> None:
        duplicate_pairs = (
            ("true", "TRUE"),
            ("1", "01"),
            ("null", "~"),
            ("1", "1.0"),
            ("0x10", "16"),
            ("0o20", "16"),
        )
        for first, second in duplicate_pairs:
            with self.subTest(first=first, second=second), tempfile.TemporaryDirectory() as temp_dir:
                skills_root = Path(temp_dir) / "skills"
                bundle = skills_root / "duplicate"
                bundle.mkdir(parents=True)
                (bundle / "SKILL.md").write_text(
                    "---\n"
                    "name: duplicate\n"
                    "description: d\n"
                    f"{first}: first\n"
                    f"{second}: second\n"
                    "---\n\nBody\n",
                    encoding="utf-8",
                )

                with patch("src.agents.deepseek_harness.skills.subprocess.run") as run_mock:
                    with self.assertRaisesRegex(DshSkillError, "duplicate YAML mapping key"):
                        install_dsh_skills("dsh-task", "duplicate\n", str(skills_root))

                run_mock.assert_not_called()

    def test_install_rejects_frontmatter_delimiters_ignored_by_dsh(self) -> None:
        for opening, closing in (("--- ", "---"), ("---", " ---"), ("---", "--- ")):
            with (
                self.subTest(opening=opening, closing=closing),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                skills_root = Path(temp_dir) / "skills"
                bundle = skills_root / "invalid-delimiter"
                bundle.mkdir(parents=True)
                (bundle / "SKILL.md").write_text(
                    f"{opening}\nname: invalid-delimiter\ndescription: d\n{closing}\nBody\n",
                    encoding="utf-8",
                )

                with patch("src.agents.deepseek_harness.skills.subprocess.run") as run_mock:
                    with self.assertRaisesRegex(
                        DshSkillError,
                        "missing YAML frontmatter|unterminated YAML frontmatter",
                    ):
                        install_dsh_skills(
                            "dsh-task",
                            "invalid-delimiter\n",
                            str(skills_root),
                        )

                run_mock.assert_not_called()

    def test_install_skips_missing_bundle_like_existing_skill_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_root = Path(temp_dir) / "skills"
            self._write_skill(skills_root, "present", name="present")
            copied_commands: list[list[str]] = []
            missing: list[str] = []

            def fake_run(
                command: list[str],
                **_kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                if command[:2] == ["docker", "cp"]:
                    copied_commands.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            with (
                self.assertLogs(
                    "src.agents.deepseek_harness.skills",
                    level="WARNING",
                ) as logs,
                patch(
                    "src.agents.deepseek_harness.skills.subprocess.run",
                    side_effect=fake_run,
                ),
            ):
                names = install_dsh_skills(
                    "dsh-task",
                    "present\nmissing\n",
                    str(skills_root),
                    on_missing=missing.append,
                )

            self.assertEqual(names, ["present"])
            self.assertEqual(len(copied_commands), 1)
            self.assertEqual(missing, ["missing"])
            self.assertRegex("\n".join(logs.output), "missing.*skipping")


if __name__ == "__main__":
    unittest.main()
