"""Tests for the extension task authoring validator."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.validate_extension_tasks import SHORT_ID_RE, validate_repository  # noqa: E402


TASK_ID = "01_Productivity_Flow_task_001_fixture"
CATEGORY = "01_Productivity_Flow"


VALID_TASK = """\
---
id: 01_Productivity_Flow_task_001_fixture
name: Fixture task
category: 01_Productivity_Flow
timeout_seconds: 180
modality: pure-text
difficulty: L2
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3
tags:
  - custom
---

## Prompt

Read `/tmp_workspace/input.txt` and save the answer to
`/tmp_workspace/results/answer.json`.

## Automated Checks

```python
def grade(transcript: list, workspace_path: str) -> dict:
    scores = {
        "fact": 1.0,
        "delivery": 1.0,
        "overall_score": 1.0,
    }
    return scores
```

## LLM Judge Rubric

### Criterion 1: Quality (key: quality, weight: 1.0)

**Score 1.0**: All required reasoning is explicit and correct.

**Score 0.75**: One minor supporting detail is missing.

**Score 0.5**: The core answer is present but incomplete.

**Score 0.25**: Only a relevant fragment is present.

**Score 0.0**: The answer is absent or unrelated.

## Workspace Path

```
workspace/extension/01_Productivity_Flow/task_001_fixture
```
"""


VALID_SOURCES = """\
schema_version: 1
retrieved_at: "2026-08-01"
registry_contract:
  active_task_count: 1
  category_task_counts:
    01_Productivity_Flow: 1
  reserved_invalid_short_ids: []
tasks:
  - short_id: "01-001"
    task_id: 01_Productivity_Flow_task_001_fixture
    design_origin:
      type: public
      verification_status: page_verified
      human_authorship: not_independently_verifiable
      request_summary: Fixture request.
      adaptation_note: Fixture adaptation.
      references:
        - kind: github_issue
          url: https://example.org/issues/1
          title: Fixture issue
    runtime_sources: []
excluded_tasks: []
"""


VALID_CAPABILITIES = """\
01_Productivity_Flow_task_001_fixture:
  automated.fact: [data_processing]
  automated.delivery: [verification_delivery]
  llm_judge.quality: [content_generation, reasoning_planning]
"""


class ExtensionTaskValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.task_dir = self.root / "tasks" / "extension" / CATEGORY
        self.workspace_dir = (
            self.root
            / "workspace"
            / "extension"
            / CATEGORY
            / "task_001_fixture"
        )
        self.map_path = (
            self.root
            / "tools"
            / "report"
            / "data"
            / "checkpoint_capability_map7.yaml"
        )
        self.task_path = self.task_dir / f"{TASK_ID}.md"
        self.sources_path = self.root / "tasks" / "extension" / "task_sources.yaml"

        (self.workspace_dir / "exec").mkdir(parents=True)
        (self.workspace_dir / "gt").mkdir(parents=True)
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self.map_path.parent.mkdir(parents=True)
        (self.workspace_dir / "exec" / "input.txt").write_text(
            "fixture", encoding="utf-8"
        )
        (self.workspace_dir / "gt" / "expected.json").write_text(
            "{}", encoding="utf-8"
        )
        self.task_path.write_text(VALID_TASK, encoding="utf-8")
        self.sources_path.write_text(VALID_SOURCES, encoding="utf-8")
        self.map_path.write_text(VALID_CAPABILITIES, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def codes(self, *, allow_incomplete: bool = False) -> set[str]:
        return {
            issue.code
            for issue in validate_repository(
                self.root, allow_incomplete=allow_incomplete
            )
        }

    def test_valid_complete_fixture_passes(self):
        self.assertEqual(validate_repository(self.root), [])

    def test_task_metadata_grading_mapping_attachment_and_url_failures(self):
        content = self.task_path.read_text(encoding="utf-8")
        content = content.replace(
            "category: 01_Productivity_Flow", "category: 01_生产力工作流"
        )
        content = content.replace("difficulty: L2", "difficulty: L5")
        content = content.replace("automated: 0.7", "automated: 0.6")
        content = content.replace(
            "/tmp_workspace/input.txt", "/tmp_workspace/missing.txt"
        )
        renamed = self.task_path.with_name(f"{TASK_ID}_renamed.md")
        renamed.write_text(content, encoding="utf-8")
        self.task_path.unlink()

        source_content = self.sources_path.read_text(encoding="utf-8").replace(
            "https://example.org/issues/1", "http://example.org/issues/1"
        )
        self.sources_path.write_text(source_content, encoding="utf-8")

        self.map_path.write_text(
            """\
01_Productivity_Flow_task_001_fixture:
  automated.fact: [data_processing, unknown_dimension]
  automated.unexpected: [data_processing, tool_use, verification_delivery]
  llm_judge.quality: [content_generation, reasoning_planning]
""",
            encoding="utf-8",
        )
        large_attachment = self.workspace_dir / "exec" / "large.bin"
        with large_attachment.open("wb") as handle:
            handle.truncate(5 * 1024 * 1024 + 1)

        codes = self.codes()
        self.assertTrue(
            {
                "id.filename",
                "category.mismatch",
                "difficulty.invalid",
                "weights.sum",
                "attachment.path",
                "attachment.size",
                "url.invalid",
                "capability_map.count",
                "capability_map.label",
                "capability_map.checkpoint_extra",
                "capability_map.checkpoint_missing",
            }.issubset(codes),
            codes,
        )

    def test_category_numbering_starts_at_001_without_gaps(self):
        source_content = self.sources_path.read_text(encoding="utf-8").replace(
            "excluded_tasks: []",
            """\
  - short_id: "02-002"
    task_id: 02_Code_Intelligence_task_002_planned
    design_origin:
      type: constructed
      verification_status: constructed_from_common_need
      human_authorship: not_applicable
      request_summary: Planned fixture.
      adaptation_note: Planned fixture.
      references: []
    runtime_sources: []
excluded_tasks: []""",
        )
        self.sources_path.write_text(source_content, encoding="utf-8")

        issues = validate_repository(self.root, allow_incomplete=True)
        self.assertTrue(
            any(
                issue.code == "numbering.gap"
                and "02_Code_Intelligence has unreserved number(s): 001" in issue.message
                for issue in issues
            ),
            issues,
        )

    def test_prompt_attachment_path_cannot_escape_workspace(self):
        content = self.task_path.read_text(encoding="utf-8").replace(
            "/tmp_workspace/input.txt", "/tmp_workspace/../outside.txt"
        )
        self.task_path.write_text(content, encoding="utf-8")
        (self.workspace_dir / "outside.txt").write_text("outside", encoding="utf-8")

        self.assertIn("attachment.path", self.codes())

    def test_zero_number_is_not_a_valid_task_number(self):
        self.task_path.write_text(
            self.task_path.read_text(encoding="utf-8").replace("001", "000"),
            encoding="utf-8",
        )
        zero_task_path = self.task_path.with_name(
            "01_Productivity_Flow_task_000_fixture.md"
        )
        self.task_path.rename(zero_task_path)
        self.sources_path.write_text(
            self.sources_path.read_text(encoding="utf-8").replace("001", "000"),
            encoding="utf-8",
        )
        self.map_path.write_text(
            self.map_path.read_text(encoding="utf-8").replace("001", "000"),
            encoding="utf-8",
        )
        self.workspace_dir.rename(self.workspace_dir.with_name("task_000_fixture"))

        codes = self.codes()
        self.assertIn("id.format", codes)
        self.assertIsNone(SHORT_ID_RE.fullmatch("01-000"))

    def test_unicode_and_ground_truth_prompt_paths_are_rejected(self):
        original = self.task_path.read_text(encoding="utf-8")
        for invalid_path in (
            "/tmp_workspace/不存在.txt",
            "/tmp_workspace/gt/expected.json",
        ):
            with self.subTest(path=invalid_path):
                self.task_path.write_text(
                    original.replace("/tmp_workspace/input.txt", invalid_path),
                    encoding="utf-8",
                )
                self.assertIn("attachment.path", self.codes())

    def test_workspace_subdirectories_cannot_be_symlinks(self):
        exec_dir = self.workspace_dir / "exec"
        actual_exec = self.workspace_dir / "actual_exec"
        exec_dir.rename(actual_exec)
        exec_dir.symlink_to(actual_exec, target_is_directory=True)

        self.assertIn("workspace.symlink", self.codes())

    def test_large_gitkeep_still_respects_attachment_limit(self):
        placeholder = self.workspace_dir / "exec" / ".gitkeep"
        with placeholder.open("wb") as handle:
            handle.truncate(5 * 1024 * 1024 + 1)

        self.assertIn("attachment.size", self.codes())

    def test_nested_capability_label_reports_issue_instead_of_crashing(self):
        self.map_path.write_text(
            VALID_CAPABILITIES.replace("[data_processing]", "[[data_processing]]"),
            encoding="utf-8",
        )

        self.assertIn("capability_map.label", self.codes())

    def test_nonhybrid_weights_reject_extra_fields(self):
        content = self.task_path.read_text(encoding="utf-8").replace(
            """\
grading_type: hybrid
grading_weights:
  automated: 0.7
  llm_judge: 0.3""",
            """\
grading_type: llm_judge
grading_weights:
  automated: 0.0
  llm_judge: 1.0
  unexpected: 99""",
        )
        self.task_path.write_text(content, encoding="utf-8")

        self.assertIn("weights.fields", self.codes())

    def test_malformed_https_urls_are_rejected(self):
        original = self.sources_path.read_text(encoding="utf-8")
        for invalid_url in (
            "https://bad_host.example/issues/1",
            "https://example.org/%ZZ",
            "https://999.999.999.999/issues/1",
            "https://localhost/issues/1",
        ):
            with self.subTest(url=invalid_url):
                self.sources_path.write_text(
                    original.replace("https://example.org/issues/1", invalid_url),
                    encoding="utf-8",
                )
                self.assertIn("url.invalid", self.codes())

    def test_reserved_invalid_number_cannot_be_reused(self):
        source_content = self.sources_path.read_text(encoding="utf-8").replace(
            "excluded_tasks: []",
            """\
excluded_tasks:
  - short_id: "01-001"
    task_id: 01_Productivity_Flow_task_001_retired_fixture
    status: invalid
    number_reserved: true""",
        )
        self.sources_path.write_text(source_content, encoding="utf-8")

        codes = self.codes()
        self.assertIn("numbering.reused", codes)
        self.assertIn("short_id.duplicate", codes)

    def test_registry_contract_locks_counts_and_invalid_reservations(self):
        source_content = self.sources_path.read_text(encoding="utf-8")
        source_content = source_content.replace("active_task_count: 1", "active_task_count: 2")
        source_content = source_content.replace(
            "reserved_invalid_short_ids: []",
            'reserved_invalid_short_ids: ["04-001"]',
        )
        self.sources_path.write_text(source_content, encoding="utf-8")

        codes = self.codes()
        self.assertIn("sources.contract_count", codes)
        self.assertIn("sources.contract_invalid", codes)

    def test_strict_mode_reports_planned_task_missing(self):
        source_content = self.sources_path.read_text(encoding="utf-8").replace(
            "excluded_tasks: []",
            """\
  - short_id: "01-002"
    task_id: 01_Productivity_Flow_task_002_planned
    design_origin:
      type: constructed
      verification_status: constructed_from_common_need
      human_authorship: not_applicable
      request_summary: Planned fixture.
      adaptation_note: Planned fixture.
      references: []
    runtime_sources: []
excluded_tasks: []""",
        )
        self.sources_path.write_text(source_content, encoding="utf-8")

        self.assertIn("task.missing", self.codes())
        self.assertNotIn("task.missing", self.codes(allow_incomplete=True))

    def test_rubric_requires_all_five_declared_bands(self):
        content = self.task_path.read_text(encoding="utf-8").replace(
            "**Score 0.25**: Only a relevant fragment is present.\n\n", ""
        )
        self.task_path.write_text(content, encoding="utf-8")

        self.assertIn("rubric.bands", self.codes())


if __name__ == "__main__":
    unittest.main()
