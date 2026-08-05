"""Executable checks for the nine remaining Creative Synthesis extension tasks."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.utils.task_parser import parse_task_md  # noqa: E402
from tools.validate_extension_tasks import validate_repository  # noqa: E402


CATEGORY = "05_Creative_Synthesis"
TASKS = {
    "05_Creative_Synthesis_task_001_book_club_opening": "task_001_book_club_opening",
    "05_Creative_Synthesis_task_002_release_note_rewrite": "task_002_release_note_rewrite",
    "05_Creative_Synthesis_task_003_brand_name_directions": "task_003_brand_name_directions",
    "05_Creative_Synthesis_task_004_feedback_to_launch_script": "task_004_feedback_to_launch_script",
    "05_Creative_Synthesis_task_005_branching_dialogue": "task_005_branching_dialogue",
    "05_Creative_Synthesis_task_006_podcast_storyboard": "task_006_podcast_storyboard",
    "05_Creative_Synthesis_task_008_accessible_timeline_microsite": "task_008_accessible_timeline_microsite",
    "05_Creative_Synthesis_task_009_accessibility_law_cards": "task_009_accessibility_law_cards",
    "05_Creative_Synthesis_task_010_apollo_museum_narrative": "task_010_apollo_museum_narrative",
}
EXPECTED_METADATA = {
    "05_Creative_Synthesis_task_001_book_club_opening": ("L1", "llm_judge", 0.0, 1.0),
    "05_Creative_Synthesis_task_002_release_note_rewrite": ("L1", "hybrid", 0.4, 0.6),
    "05_Creative_Synthesis_task_003_brand_name_directions": ("L2", "llm_judge", 0.0, 1.0),
    "05_Creative_Synthesis_task_004_feedback_to_launch_script": ("L2", "hybrid", 0.4, 0.6),
    "05_Creative_Synthesis_task_005_branching_dialogue": ("L3", "hybrid", 0.4, 0.6),
    "05_Creative_Synthesis_task_006_podcast_storyboard": ("L2", "hybrid", 0.4, 0.6),
    "05_Creative_Synthesis_task_008_accessible_timeline_microsite": ("L4", "hybrid", 0.7, 0.3),
    "05_Creative_Synthesis_task_009_accessibility_law_cards": ("L3", "hybrid", 0.4, 0.6),
    "05_Creative_Synthesis_task_010_apollo_museum_narrative": ("L4", "hybrid", 0.4, 0.6),
}
EXPECTED_AUTO_KEYS = {
    "05_Creative_Synthesis_task_002_release_note_rewrite": {"word_limit", "feature_tokens", "required_format"},
    "05_Creative_Synthesis_task_004_feedback_to_launch_script": {"feedback_references", "length_range", "single_script_format"},
    "05_Creative_Synthesis_task_005_branching_dialogue": {"yaml_schema", "state_reachability", "condition_logic", "convergence"},
    "05_Creative_Synthesis_task_006_podcast_storyboard": {"storyboard_schema", "duration_and_shots", "quote_traceability"},
    "05_Creative_Synthesis_task_008_accessible_timeline_microsite": {
        "single_file_offline", "event_fidelity_order", "keyboard_behavior",
        "semantic_accessibility", "runtime_integrity",
    },
    "05_Creative_Synthesis_task_009_accessibility_law_cards": {"six_card_structure", "citation_shape", "theme_coverage"},
    "05_Creative_Synthesis_task_010_apollo_museum_narrative": {"official_id_url", "required_sections", "length_and_labels"},
}
EXPECTED_JUDGE_WEIGHTS = {
    "05_Creative_Synthesis_task_001_book_club_opening": {
        "brief_requirements": 0.25, "spoken_structure": 0.25, "tone_fit": 0.25, "ready_to_use": 0.25,
    },
    "05_Creative_Synthesis_task_002_release_note_rewrite": {
        "fact_fidelity": 0.416667, "user_readability": 0.333333, "publish_ready": 0.25,
    },
    "05_Creative_Synthesis_task_003_brand_name_directions": {
        "three_directions": 0.25, "constraint_fit": 0.25,
        "direction_distinctness": 0.25, "rationale_usefulness": 0.25,
    },
    "05_Creative_Synthesis_task_004_feedback_to_launch_script": {
        "faithful_synthesis": 0.333333, "balanced_message": 0.25,
        "spoken_flow": 0.25, "stage_readiness": 0.166667,
    },
    "05_Creative_Synthesis_task_005_branching_dialogue": {
        "character_consistency": 0.333333, "dialogue_naturalness": 0.333333, "choice_clarity": 0.333334,
    },
    "05_Creative_Synthesis_task_006_podcast_storyboard": {
        "selection_arc": 0.333333, "visual_feasibility": 0.25,
        "subtitle_quality": 0.25, "editor_readiness": 0.166667,
    },
    "05_Creative_Synthesis_task_008_accessible_timeline_microsite": {
        "narrative_scanability": 0.5, "interaction_usability": 0.5,
    },
    "05_Creative_Synthesis_task_009_accessibility_law_cards": {
        "legal_factuality": 0.5, "plain_language_fit": 0.25, "card_actionability": 0.25,
    },
    "05_Creative_Synthesis_task_010_apollo_museum_narrative": {
        "fact_fidelity": 0.416667, "source_transition_separation": 0.25,
        "museum_arc": 0.166667, "family_audience_fit": 0.166666,
    },
}


def task_path(task_id: str) -> Path:
    return REPO_ROOT / "tasks" / "extension" / CATEGORY / f"{task_id}.md"


def workspace_path(task_id: str) -> Path:
    return REPO_ROOT / "workspace" / "extension" / CATEGORY / TASKS[task_id]


def metadata(task_id: str) -> dict:
    text = task_path(task_id).read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    assert match
    return yaml.safe_load(match.group(1))


def load_grader(task_id: str):
    code = parse_task_md(task_path(task_id))["automated_checks"]
    namespace: dict = {}
    exec(compile(code, str(task_path(task_id)), "exec"), namespace)
    return namespace["grade"]


def copy_workspace(task_id: str, root: Path) -> None:
    source = workspace_path(task_id)
    shutil.copytree(source / "exec", root, dirs_exist_ok=True)
    shutil.copytree(source / "gt", root / "gt")


def transcript(text: str) -> list[dict]:
    return [{"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}]


def full_direct_response(task_id: str) -> str:
    if task_id.endswith("release_note_rewrite"):
        return (
            "A smoother everyday update\n\n"
            "Focus Mode now keeps pinned tabs active, CSV Export preserves local timestamps, "
            "and Sync can retry interrupted uploads, making it easier to resume common tasks without losing context."
        )
    if task_id.endswith("feedback_to_launch_script"):
        text = (
            "今天想和大家介绍一款帮助家人共同安排出行的新工具。内测用户第一次建立共享行程时，很快就能完成基本设置，这让临时计划更容易落地。[F1]"
            "即使在地铁里没有网络，之前同步过的路线仍然可以查看，通勤途中也能继续确认安排。[F3]"
            "同时，反馈也提醒我们，家庭成员之间的权限目前还不够直观，需要更清楚地说明谁能查看和修改内容。[F2]"
            "默认通知对部分用户来说有些频繁，使用时需要按自己的节奏调整。[F4]"
            "完整路线导出目前还要经过几个步骤，也会影响需要留档或转发的人。[F5]"
            "这些声音让我们看到，共享和离线查看已经带来实际便利，但权限、通知和导出体验仍需继续打磨。"
        )
        while len(re.findall(r"[\u4e00-\u9fff]", text)) < 220:
            text += "我们会继续听取真实使用感受，让后续改进保持清楚、克制并能够被用户验证。"
        return text
    if task_id.endswith("branching_dialogue"):
        return """- id: start
  speaker: Mara
  text: 档案室今晚封门了。先告诉我，你有没有那把铜钥匙？
  condition: always
  choices:
    - text: 我带着钥匙。
      next: with_key
    - text: 我还没有钥匙。
      next: without_key
- id: with_key
  speaker: Mara
  text: 那就握紧它。门后的旧书架不稳，进去后别碰最上层。
  condition: has_archive_key == true
  choices:
    - text: 我会小心，然后离开这里。
      next: exit
- id: without_key
  speaker: Mara
  text: 先去问值夜的抄写员，他把备用钥匙的线索夹在借阅册里。
  condition: has_archive_key == false
  choices:
    - text: 我去查看借阅册。
      next: exit
- id: exit
  speaker: Mara
  text: 等你准备好再回来。
  condition: always
  choices: []"""
    if task_id.endswith("accessibility_law_cards"):
        url = "https://www.gov.cn/yaowen/liebiao/202306/content_6888910.htm"
        rows = [
            ("设施建设", "第十二条", "新建、改建或扩建公共场所、道路和交通设施时，应当符合无障碍设施工程建设标准，并让无障碍设施与主体工程同步规划、设计、施工、验收和交付使用。"),
            ("设施维护", "第二十六条", "无障碍设施建成后不能只看有没有。所有权人或者管理人应当维修损坏设施和标识、改造需要更新的设施、纠正占用行为，并做好必要维护，保障功能正常和使用安全。"),
            ("信息交流", "第三十二条", "财政资金建立的网站、服务平台和应用程序，应当逐步符合无障碍网站设计和国家信息无障碍标准。法律对其他生活服务领域使用的是国家鼓励逐步改进，强度并不完全相同。"),
            ("公共服务", "第三十九条", "公共服务场所应当配备必要的无障碍设备和辅助器具，清楚标注设施指引，并为残疾人、老年人提供无障碍服务。居民遇到服务障碍时，可以先确认场所是否提供这些基本安排。"),
            ("监督反馈", "第六十二条", "任何组织和个人都有权向主管部门提出无障碍建设意见和建议，也可以对违反法律规定的行为投诉、举报。主管部门接到相关投诉举报后，应当及时处理并给予答复。"),
            ("法律责任", "第六十五条", "无障碍设施责任人不维护、临时设施不合规，或者擅自改变用途、非法占用损坏设施时，主管部门先责令限期改正；只有逾期未改正，才按该条规定对单位或个人处以相应罚款。"),
        ]
        return "\n\n".join(
            f"### 卡片{i}｜{theme}\n正文：{body}\n条款：{article}\n来源：{url}"
            for i, (theme, article, body) in enumerate(rows, 1)
        )
    if task_id.endswith("apollo_museum_narrative"):
        act1 = (
            "Apollo 11 left Kennedy Space Center at 8:32 a.m. EST on July 16, 1969. "
            "The spacecraft entered lunar orbit at approximately 76 hours of ground elapsed time. "
        )
        act2 = (
            "The lunar module landed in the Sea of Tranquility at 102:45:40. "
            "Armstrong first contacted the surface at 109:24:15, or 9:56:15 p.m. EST on July 20. "
        )
        act3 = (
            "The ascent stage lifted off at about 124.25 hours and docking followed at 128 hours. "
            "The command module later landed in the Pacific near 195.25 hours, and the crew reached USS Hornet. "
        )
        text = (
            "# Opening\nFamilies, this account follows the official Apollo 11 mission report. "
            "[Narrative transition: Imagine following a clock that began at launch.]\n\n"
            f"## Act 1\n{act1}[Narrative transition: The journey now turns toward the Moon.]\n"
            "[Source note: NASA-SP-238, p. 1]\n\n"
            f"## Act 2\n{act2}[Narrative transition: A distant target becomes a place where people can work.]\n"
            "[Source note: NASA-SP-238, p. 1]\n\n"
            f"## Act 3\n{act3}"
        )
        filler = (
            "The report records each stage through measured times, spacecraft actions, and observations, "
            "allowing visitors to connect careful preparation with the sequence of the mission. "
        )
        while len(re.findall(r"[A-Za-z]+(?:[-’'][A-Za-z]+)*|\d+(?:\.\d+)?", text)) < 625:
            text += filler
        text += (
            "[Narrative transition: The mission ends with a return to people waiting at sea.]\n"
            "[Source note: NASA-SP-238, p. 2]\n\n"
            "## Closing Question\nWhich part of this carefully timed journey would you want to understand better?\n\n"
            "Source: NASA-SP-238, Document ID 19710015566; "
            "https://ntrs.nasa.gov/citations/19710015566 ; "
            "https://ntrs.nasa.gov/api/citations/19710015566/downloads/19710015566.pdf"
        )
        return text
    raise AssertionError(task_id)


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def full_timeline_html(data: dict) -> str:
    items = []
    for event in data["events"]:
        items.append(
            f'''<li><button type="button" data-event-id="{event['id']}" aria-expanded="false" aria-controls="details-{event['id']}">'''
            f'''<span class="event-id">{event['id']}</span><time datetime="{event['date']}">{event['date']}</time>'''
            f'''<strong>{event['title']}</strong></button><div id="details-{event['id']}" hidden><p>{event['description']}</p></div></li>'''
        )
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Project timeline</title><style>*{{box-sizing:border-box}}html,body{{max-width:100%;overflow-x:hidden}}body{{margin:0;font-family:system-ui,sans-serif}}main{{max-width:48rem;margin:auto;padding:1rem;overflow-wrap:anywhere}}li{{margin:1rem 0}}button{{width:100%;text-align:left;padding:1rem}}button:focus-visible{{outline:3px solid #0645ad;outline-offset:3px}}[hidden]{{display:none}}@media (max-width: 420px){{main{{padding:.75rem}}button{{padding:.75rem}}}}@media (prefers-reduced-motion: reduce){{*{{animation:none!important;transition:none!important;scroll-behavior:auto!important}}}}</style></head>
<body><main><h1>Project timeline</h1><p>Open an event to read how the project developed.</p><ol>{''.join(items)}</ol></main>
<script>document.querySelectorAll('button[data-event-id]').forEach(button=>{{const details=document.getElementById(button.getAttribute('aria-controls'));const toggle=()=>{{const expanded=button.getAttribute('aria-expanded')==='true';button.setAttribute('aria-expanded',String(!expanded));details.hidden=expanded;}};button.addEventListener('click',toggle);button.addEventListener('keydown',event=>{{if(event.key==='Enter'||event.key===' '){{event.preventDefault();toggle();}}}});}});</script></body></html>'''


def write_full(task_id: str, root: Path) -> list[dict]:
    if task_id in EXPECTED_AUTO_KEYS and any(task_id.endswith(suffix) for suffix in (
        "release_note_rewrite", "feedback_to_launch_script", "branching_dialogue",
        "accessibility_law_cards", "apollo_museum_narrative",
    )):
        return transcript(full_direct_response(task_id))
    data = json.loads((root / "gt/expected.json").read_text(encoding="utf-8"))
    results = root / "results"
    results.mkdir()
    if task_id.endswith("podcast_storyboard"):
        rows = []
        times = [(0, 12), (12, 25), (25, 38), (38, 50), (50, 63), (63, 76), (76, 89)]
        for number, ((timecode, quote), (start, end)) in enumerate(zip(list(data["quotes"].items())[:7], times), 1):
            rows.append({
                "shot": number, "start_sec": start, "end_sec": end,
                "source_timecode": timecode, "spoken_quote": quote["text"],
                "subtitle": quote["text"][:18], "visual_note": "普通办公室桌面近景与简单文字动画",
            })
        write_csv(results / "storyboard.csv", data["columns"], rows)
    elif task_id.endswith("accessible_timeline_microsite"):
        (results / "index.html").write_text(full_timeline_html(data), encoding="utf-8")
    else:
        raise AssertionError(task_id)
    return []


def write_partial(task_id: str, root: Path) -> list[dict]:
    tr = write_full(task_id, root)
    if task_id.endswith("release_note_rewrite"):
        tr = transcript(full_direct_response(task_id).replace("and Sync can retry interrupted uploads, ", ""))
    elif task_id.endswith("feedback_to_launch_script"):
        tr = transcript(full_direct_response(task_id).replace("[F5]", ""))
    elif task_id.endswith("branching_dialogue"):
        tr = transcript(full_direct_response(task_id).replace("next: exit\n- id: exit", "next: without_key\n- id: exit", 1))
    elif task_id.endswith("podcast_storyboard"):
        path = root / "results/storyboard.csv"
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle); columns = reader.fieldnames or []; rows = list(reader)
        rows[0]["spoken_quote"] += "改写"
        write_csv(path, columns, rows)
    elif task_id.endswith("accessible_timeline_microsite"):
        path = root / "results/index.html"
        path.write_text(path.read_text(encoding="utf-8").replace("event.key===' '", "event.key==='Escape'"), encoding="utf-8")
    elif task_id.endswith("accessibility_law_cards"):
        tr = transcript(full_direct_response(task_id).replace(
            "来源：https://www.gov.cn/yaowen/liebiao/202306/content_6888910.htm",
            "来源：中国政府网",
            1,
        ))
    elif task_id.endswith("apollo_museum_narrative"):
        tr = transcript(full_direct_response(task_id).replace("Document ID 19710015566", "official record", 1))
    return tr


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CreativeSynthesisExtensionTaskTest(unittest.TestCase):
    def test_metadata_matches_blueprint(self):
        for task_id, wanted in EXPECTED_METADATA.items():
            with self.subTest(task_id=task_id):
                difficulty, grading_type, auto_weight, judge_weight = wanted
                actual = metadata(task_id)
                self.assertEqual((actual["difficulty"], actual["grading_type"]), (difficulty, grading_type))
                self.assertAlmostEqual(actual["grading_weights"]["automated"], auto_weight)
                self.assertAlmostEqual(actual["grading_weights"]["llm_judge"], judge_weight)

    def test_static_validator_accepts_current_repository(self):
        self.assertEqual(validate_repository(REPO_ROOT, allow_incomplete=True), [])
        strict = validate_repository(REPO_ROOT)
        self.assertEqual(strict, [])

    def test_auto_graders_have_full_partial_zero_tiers(self):
        for task_id in EXPECTED_AUTO_KEYS:
            with self.subTest(task_id=task_id):
                grade = load_grader(task_id)
                tier_scores = {}
                for tier in ("full", "partial", "zero"):
                    with tempfile.TemporaryDirectory(prefix="creative-grade-") as temporary:
                        root = Path(temporary)
                        copy_workspace(task_id, root)
                        tr = []
                        if tier == "full":
                            tr = write_full(task_id, root)
                        elif tier == "partial":
                            tr = write_partial(task_id, root)
                        result = grade(transcript=tr, workspace_path=str(root))
                        self.assertEqual(set(result) - {"overall_score"}, EXPECTED_AUTO_KEYS[task_id])
                        tier_scores[tier] = float(result["overall_score"])
                self.assertAlmostEqual(tier_scores["full"], 1.0, places=6)
                self.assertGreater(tier_scores["partial"], 0.0)
                self.assertLess(tier_scores["partial"], 1.0)
                self.assertAlmostEqual(tier_scores["zero"], 0.0, places=6)

    def test_direct_reply_grader_accepts_backend_neutral_message_shapes(self):
        task_id = "05_Creative_Synthesis_task_002_release_note_rewrite"
        response = full_direct_response(task_id)
        variants = [
            [{"role": "assistant", "content": response}],
            [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": response}]}],
            [{"message": {"role": "assistant", "content": [{"type": "text", "text": {"value": response}}]}}],
        ]
        grade = load_grader(task_id)
        for variant in variants:
            with self.subTest(shape=variant):
                self.assertEqual(grade(transcript=variant, workspace_path="/tmp_workspace")["overall_score"], 1.0)

    def test_judge_rubrics_have_five_bands_and_weights(self):
        required = {"1.0", "0.75", "0.5", "0.25", "0.0"}
        pattern = re.compile(r"\*\*Score\s+(1\.0|0\.75|0\.5|0\.25|0\.0)\*\*:")
        for task_id, wanted in EXPECTED_JUDGE_WEIGHTS.items():
            with self.subTest(task_id=task_id):
                criteria = parse_task_md(task_path(task_id))["rubric_criteria"]
                actual = {item["key"]: item["weight"] for item in criteria}
                self.assertEqual(set(actual), set(wanted))
                self.assertAlmostEqual(sum(actual.values()), 1.0, places=6)
                for key, weight in wanted.items():
                    self.assertAlmostEqual(actual[key], weight, places=6)
                for criterion in criteria:
                    self.assertEqual(set(pattern.findall(criterion["rubric"])), required)

    def test_capability_mapping_is_complete(self):
        mapping = yaml.safe_load((REPO_ROOT / "tools/report/data/checkpoint_capability_map7.yaml").read_text(encoding="utf-8"))
        for task_id in TASKS:
            judge = {f"llm_judge.{key}" for key in EXPECTED_JUDGE_WEIGHTS[task_id]}
            auto = {f"automated.{key}" for key in EXPECTED_AUTO_KEYS.get(task_id, set())}
            self.assertEqual(set(mapping[task_id]), judge | auto)

    def test_attachment_hash_size_and_gt_consistency(self):
        attachment_tasks = {
            "05_Creative_Synthesis_task_006_podcast_storyboard": 2,
            "05_Creative_Synthesis_task_008_accessible_timeline_microsite": 2,
        }
        for task_id in TASKS:
            with self.subTest(task_id=task_id):
                ws = workspace_path(task_id)
                data = json.loads((ws / "gt/expected.json").read_text(encoding="utf-8"))
                files = [path for path in (ws / "exec").rglob("*") if path.is_file() and path.name != ".gitkeep"]
                self.assertEqual(len(files), attachment_tasks.get(task_id, 0))
                self.assertLess(sum(path.stat().st_size for path in files), 5 * 1024 * 1024)
                if files:
                    actual = {str(path.relative_to(ws / "exec")): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
                    self.assertEqual(actual, data["exec_file_sha256"])
                forbidden = [path for path in ws.rglob("*") if path.is_file() and path.suffix.lower() in {".pdf", ".warc", ".mhtml"}]
                self.assertEqual(forbidden, [])

    def test_runtime_sources_and_prompt_modes(self):
        registry = yaml.safe_load((REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8"))
        records = {item["task_id"]: item for item in registry["tasks"] if item["task_id"] in TASKS}
        self.assertEqual(set(records), set(TASKS))
        runtime_urls = []
        for task_id, record in records.items():
            prompt = parse_task_md(task_path(task_id))["prompt"]
            urls = [source["url"] for source in record["runtime_sources"]]
            runtime_urls.extend(urls)
            for url in urls:
                self.assertIn(url, prompt)
            if task_id.endswith(("accessibility_law_cards", "apollo_museum_narrative")):
                self.assertTrue(urls)
            else:
                self.assertEqual(urls, [])
        self.assertEqual(len(runtime_urls), 3)

    @unittest.skipUnless(os.environ.get("WILDCLAW_RUN_NETWORK_TESTS") == "1", "enable host URL checks explicitly")
    def test_fixed_urls_are_reachable(self):
        registry = yaml.safe_load((REPO_ROOT / "tasks/extension/task_sources.yaml").read_text(encoding="utf-8"))
        urls = [source["url"] for item in registry["tasks"] if item["task_id"] in TASKS for source in item["runtime_sources"]]
        for url in urls:
            with self.subTest(url=url):
                completed = subprocess.run([
                    "/usr/bin/curl", "--location", "--silent", "--show-error", "--output", "/dev/null",
                    "--write-out", "%{http_code}", "--connect-timeout", "15", "--max-time", "60",
                    "--user-agent", "WildClawBench/1.0 evaluation@example.com", url,
                ], capture_output=True, text=True, timeout=70)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertTrue(200 <= int(completed.stdout) < 400)

    def test_report_and_low_score_tools_discover_tasks(self):
        report = load_module("creative_report", REPO_ROOT / "tools/report/scripts/generate_eval_report.py")
        manifest = load_module("creative_manifest", REPO_ROOT / "tools/report/skills/low-score-analysis/scripts/generate_failed_tasks_manifest.py")
        rows = report.load_all_task_meta(REPO_ROOT / "tasks")
        for task_id in TASKS:
            self.assertIn(task_id, rows)
            self.assertEqual(rows[task_id]["suite"], CATEGORY)
            located = manifest.locate_task_file(REPO_ROOT / "tasks", CATEGORY, task_id)
            self.assertEqual(Path(located), task_path(task_id))

    def test_prompts_are_user_facing_and_outputs_bounded(self):
        banned = ("评测框架", "评分点", "能力维度", "llm judge", "auto评分")
        for task_id in TASKS:
            prompt = parse_task_md(task_path(task_id))["prompt"]
            for term in banned:
                self.assertNotIn(term, prompt.lower())
            self.assertNotIn("/tmp_workspace/result/", prompt)
            if task_id.endswith(("podcast_storyboard", "accessible_timeline_microsite")):
                self.assertIn("/tmp_workspace/results/", prompt)


if __name__ == "__main__":
    unittest.main()
