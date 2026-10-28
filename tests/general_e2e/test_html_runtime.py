"""HTML evidence protocol; opt-in real Chromium tests are distinct from fixtures."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from src.wildclawbench_grading_core import html_runtime as H
from tests.general_e2e.test_local_scoring_runtime import Fixture, LOCK_PATH, RUNTIME

ROOT = Path(__file__).resolve().parents[2]
HTML_ENV = ("GENERAL_E2E_HTML_NODE", "GENERAL_E2E_HTML_CORE", "GENERAL_E2E_HTML_BROWSER")


class HtmlLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        library = self.root / "core"
        library.mkdir()
        (library / "package.json").write_text(json.dumps({"name": "playwright-core", "version": "fixture-only"}), encoding="utf-8")
        self.font = self.root / "fixture.font"
        self.font.write_bytes(b"identity fixture; not a renderable font")
        # These identities exercise lock validation only; no browser runs here.
        self.lock = H.create_html_lock(Path(sys.executable).resolve(), library, Path(sys.executable).resolve(), font_files=[self.font])

    def test_lock_schema_rejects_nested_malformed_fields_even_when_archived(self):
        mutations = [
            {"settings": {**H.SETTINGS, "quiet_ms": 0}}, {"node": []},
            {"observer_sha256": "bad"}, {"font_files": [None]},
            {"playwright_core": {**self.lock["playwright_core"], "files": [{"path": "../escape", "size": 0, "sha256": "a" * 64}]}},
            {"platform": {"system": "", "machine": "x"}},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(H.HtmlRuntimeError):
                H.validate_html_lock({**self.lock, **mutation}, require_assets=False)
        changed = copy.deepcopy(self.lock)
        changed['settings']['quiet_ms'] = 0
        self.assertEqual(H.SETTINGS['quiet_ms'], 250)
        with self.assertRaises(H.HtmlRuntimeError):
            H.validate_html_lock(changed, require_assets=False)

    def test_assets_drift_and_archival_validation_has_no_runtime_dependency(self):
        self.font.unlink()
        with self.assertRaisesRegex(H.HtmlRuntimeError, "HTML_FONT_UNAVAILABLE"):
            H.validate_html_lock(self.lock)
        H.validate_html_lock(self.lock, require_assets=False)
        self.assertEqual(len(H.html_lock_digest(self.lock)), 64)

    def test_library_extra_asset_and_symlink_are_not_silently_ignored(self):
        p = Path(self.lock["playwright_core"]["root"]) / "extra"
        p.write_bytes(b"changed")
        with self.assertRaisesRegex(H.HtmlRuntimeError, "HTML_LIBRARY_DRIFT"):
            H.validate_html_lock(self.lock)
        p.unlink()
        p.symlink_to(self.font)
        with self.assertRaisesRegex(H.HtmlRuntimeError, "HTML_LIBRARY_UNSUPPORTED"):
            H.validate_html_lock(self.lock)

    def test_bounded_probes_and_public_resources(self):
        for probes in ({}, [None], [{"id": "a", "x": True, "y": 0}], [{"id": "a", "x": float("nan"), "y": 0}], [{"id": "a", "x": 0, "y": 0, "radius": 9}]):
            with self.subTest(probes=probes), self.assertRaises(H.HtmlRuntimeError):
                H._probes(probes)
        public = self.root / "public"
        public.mkdir()
        source = public / "report.html"
        source.write_text("<p>report</p>", encoding="utf-8")
        (public / "private").mkdir()
        (public / "private/secret").write_bytes(b"not public")
        self.assertEqual(H._resources(public, source), [])
        (public / "escape").symlink_to(self.font)
        with self.assertRaisesRegex(H.HtmlRuntimeError, "HTML_RESOURCE_UNSUPPORTED"):
            H._resources(public, source)

    def test_missing_runtime_is_an_error_and_legacy_task_has_no_html_dependency(self):
        fixture = Fixture(self.root / "required", scoring_runtime={"html_render": True})
        attempt = fixture.prepare()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "HTML_RUNTIME_REQUIRED"):
            RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
        self.assertFalse((attempt / "score.json").exists())
        legacy = Fixture(self.root / "legacy")
        combined = self.root / "runtime.json"
        value = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        value["html_runtime"] = {"intentionally": "invalid; legacy must ignore it"}
        combined.write_text(json.dumps(value), encoding="utf-8")
        prepared = RUNTIME.prepare_attempt(unit_root=legacy.unit_root, execution_record_path=legacy.execution_record,
            scoring_package=legacy.scoring_package, task_id=legacy.task_id, scoring_attempt_id="legacy",
            output_root=legacy.output_root, runtime_lock_path=combined)
        result = RUNTIME.run_rules_attempt(attempt_root=Path(prepared["attempt_root"]), runtime_python=Path(sys.executable), timeout_seconds=10)
        self.assertNotIn("html_runtime", result["audit"]["worker"])


SCENE = """<!doctype html><meta charset=utf-8><style>body{margin:0}canvas,svg{position:absolute;left:0}svg{top:0}#a{top:160px}#b{top:320px}</style>
<table style="position:absolute;top:470px"><tr><th>日期</th><th>流失率</th></tr><tr><td>09-04</td><td>25%</td></tr></table>
<svg width="200" height="120"><path d="M10 30 L190 30" stroke="red" stroke-width="4"/><path d="M10 50 L190 50" stroke="blue" style="display:none"/></svg>
<canvas id=a width=400 height=240 style="width:200px;height:120px"></canvas><canvas id=b width=400 height=240 style="width:200px;height:120px"></canvas>
<div id=host style="position:absolute;top:550px"></div><script>
const ctx=a.getContext('2d');ctx.scale(2,2);ctx.lineWidth=2;ctx.strokeStyle='red';ctx.save();ctx.beginPath();ctx.rect(0,0,80,120);ctx.clip();ctx.beginPath();ctx.moveTo(10,10);ctx.lineTo(190,10);ctx.stroke();ctx.restore();
const path=new Path2D('M10 30 L190 30');ctx.strokeStyle='blue';ctx.stroke(path);ctx.clearRect(90,25,20,10);
const other=b.getContext('2d');other.beginPath();other.rect(0,0,10,10);other.clip();other.moveTo(0,0);other.lineTo(400,240);other.stroke();b.setAttribute('width','400');other.scale(2,2);other.strokeStyle='green';other.lineWidth=2;other.moveTo(10,50);other.lineTo(190,50);other.stroke();
const root=host.attachShadow({mode:'closed'});root.innerHTML='<table><tr><td>shadow evidence</td></tr></table>';
// Candidate methods cannot replace the captured native geometry implementation.
SVGGeometryElement.prototype.isPointInStroke=()=>true;SVGGeometryElement.prototype.getTotalLength=()=>1;
</script>"""


@unittest.skipUnless(all(os.environ.get(k) for k in HTML_ENV), "set GENERAL_E2E_HTML_NODE/CORE/BROWSER for real Chromium acceptance")
class RealHtmlBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = H.create_html_lock(*(os.environ[k] for k in HTML_ENV))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.public = self.root / "public"
        self.public.mkdir()
        self.source = self.public / "report.html"

    def observe(self, html, *, probes=None, name="render", resource_root=None, timeout=30):
        self.source.write_text(html, encoding="utf-8")
        result = H.observe_html(self.source, self.lock, self.root / name, probes=probes, resource_root=resource_root, timeout_seconds=timeout)
        H.verify_html_observation(self.source, self.root / name, result["audit"], self.lock, resource_root=resource_root)
        return result, json.loads(Path(result["path"]).read_text(encoding="utf-8"))

    def test_actual_svg_canvas_dpr_path2d_clip_clear_reset_shadow_and_pixels(self):
        points = [("svg", 100, 30), ("svg-miss", 100, 80), ("hidden", 100, 50),
            ("clip-in", 40, 170), ("clip-out", 120, 170), ("path2d", 70, 190),
            ("cleared", 100, 190), ("reset", 150, 370)]
        result, obs = self.observe(SCENE, probes=[{"id": k, "x": x, "y": y, "radius": 0} for k, x, y in points])
        probes = {p["id"]: p for p in obs["probes"]}
        for key in ("svg", "clip-in", "path2d", "reset"):
            self.assertTrue(probes[key]["hits"], key)
            self.assertNotEqual(probes[key]["page_pixels"][0]["rgba"][:3], [255, 255, 255], key)
        for key in ("svg-miss", "clip-out", "cleared"):
            self.assertFalse(probes[key]["hits"], key)
            self.assertEqual(probes[key]["page_pixels"][0]["rgba"], [255, 255, 255, 255], key)
        self.assertFalse(any(h["css_visible"] for h in probes["hidden"]["hits"]))
        self.assertEqual(len(obs["projection"]["tables"]), 2)
        self.assertTrue(any(t["text"] == "shadow evidence" and t["visible"] for t in obs["projection"]["texts"]))
        self.assertEqual(obs["projection"]["svg"][0]["length"], 180)
        self.assertEqual(len(obs["projection"]["canvases"][1]["strokes"]), 1)
        self.assertEqual(len(obs["projection"]["canvases"][1]["strokes"][0]["commands"]), 2)
        H.verify_html_observation(self.source, self.root / "render", result["audit"], self.lock, archived=True)

    def test_nested_local_resources_remote_fetch_websocket_and_residual_rendering(self):
        nested = self.public / "nested"
        nested.mkdir()
        self.source = nested / "chart page.html"
        (nested / "chart.js").write_text("document.getElementById('result').textContent='local resource loaded';", encoding="utf-8")
        html = """<p id=result>unloaded</p><script src=chart.js></script><script>
fetch('https://remote.invalid/secret').catch(()=>{});new WebSocket('wss://remote.invalid/channel');
</script><canvas id=c></canvas><script>c.getContext('2d').fill(new Path2D('M0 0L20 0L20 20Z'));</script><iframe srcdoc='<p>frame</p>'></iframe>"""
        _, obs = self.observe(html, resource_root=self.public)
        self.assertTrue(any(r.get("resource") == "nested/chart.js" for r in obs["requests"]))
        self.assertTrue(any(r["result"] == "blocked" and "remote.invalid" in r["url"] for r in obs["requests"]))
        self.assertTrue(obs["websockets"])
        self.assertTrue(any(t["text"] == "local resource loaded" for t in obs["projection"]["texts"]))
        self.assertIn("fill-vector-not-observed", obs["projection"]["canvases"][0]["unsupported"])
        self.assertEqual(len(obs["projection"]["frames"]), 1)

    def test_audit_rejects_changed_bytes_resigned_context_and_resource_inventory(self):
        (self.public / "style.css").write_text("p{color:blue}", encoding="utf-8")
        result, _ = self.observe('<link rel=stylesheet href=style.css><p>evidence</p>')
        out = self.root / "render"
        audit = result["audit"]
        png = out / "page.png"
        before = png.read_bytes()
        png.write_bytes(before + b"tampered")
        with self.assertRaisesRegex(H.HtmlRuntimeError, "HTML_AUDIT_INVALID"):
            H.verify_html_observation(self.source, out, audit, self.lock, archived=True)
        png.write_bytes(before)
        request = out / "request.json"
        old = request.read_bytes()
        value = json.loads(old)
        value["source_resource_path"] = "wrong.html"
        request.write_text(json.dumps(value), encoding="utf-8")
        forged = copy.deepcopy(audit)
        forged["request_sha256"] = H.sha(request)
        for row in forged["artifacts"]:
            if row["path"] == "request.json":
                row.update(size=request.stat().st_size, sha256=H.sha(request))
        with self.assertRaisesRegex(H.HtmlRuntimeError, "request context"):
            H.verify_html_observation(self.source, out, forged, self.lock, archived=True)
        request.write_bytes(old)
        (self.public / "added.js").write_bytes(b"new asset")
        with self.assertRaisesRegex(H.HtmlRuntimeError, "resource inventory"):
            H.verify_html_observation(self.source, out, audit, self.lock, archived=True)

    @unittest.skipIf(os.name == "nt", "process status assertion uses Unix ps; Windows needs native acceptance")
    def test_timeout_terminates_node_and_browser_separate_process_groups(self):
        self.source.write_text('<script>while(true){}</script>', encoding="utf-8")
        with self.assertRaisesRegex(H.HtmlRuntimeError, "HTML_OBSERVATION_TIMEOUT"):
            H.observe_html(self.source, self.lock, self.root / "timeout", timeout_seconds=3)
        info = json.loads((self.root / "timeout/process-info.json").read_text(encoding="utf-8"))
        for pid in info.values():
            status = subprocess.run(["ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True).stdout.strip()
            self.assertTrue(not status or status.startswith("Z"), (pid, status))

    def test_worker_html_only_derivation_and_archived_score_tamper_detection(self):
        rule = '''def grade(**kwargs):
    import os,json,runpy
    from pathlib import Path
    root=Path(kwargs['workspace_path'])
    lock=json.loads(Path(os.environ['GENERAL_E2E_HTML_LOCK']).read_text(encoding='utf-8'))
    api=runpy.run_path(str(root/'gt/html_runtime.py'))
    result=api['observe_html'](root/'report.html',lock,Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])/'html')
    observation=json.loads(Path(result['path']).read_text(encoding='utf-8'))
    score=float(any(t['visible'] and 'visible evidence' in t['text'] for t in observation['projection']['texts']))
    return {'html':score,'overall_score':score}
'''
        attempt = self.worker_attempt(rule)
        result = RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=40)
        self.assertEqual(result["rule_component"]["score"], 1.0)
        self.assertIn("html_runtime", result["audit"]["worker"])
        self.assertNotIn("office_runtime", result["audit"]["worker"])
        self.assertTrue(RUNTIME._verify_html_rule_evidence(attempt, required=True))
        manifest = json.loads((attempt / "attempt-manifest.json").read_text(encoding="utf-8"))
        references, _ = RUNTIME._semantic_reference_inputs(attempt, manifest, [])
        self.assertTrue(any(r["type"] == "rule_derived_artifact" and r["path"].endswith("page.png") for r in references))
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.assertTrue(RUNTIME.verify_score_attempt(attempt)["score_valid"])
        import shutil
        shutil.rmtree(attempt / "runtime")
        self.assertTrue(RUNTIME.verify_score_attempt(attempt, archived=True)["score_valid"])
        (attempt / "worker/derived/html/page.png").write_bytes(b"changed")
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "HTML_DERIVED_ARTIFACT_DRIFT"):
            RUNTIME.verify_score_attempt(attempt, archived=True)

    def worker_attempt(self, rule, *, html='<p>visible evidence</p>', office=False):
        helper = {name: (ROOT / "src/wildclawbench_grading_core" / name).read_bytes() for name in ("html_runtime.py", "html_observer.mjs")}
        requirements = {"html_render": True, **({"office": True} if office else {})}
        fixture = Fixture(self.root / "worker", rule=rule, scoring_runtime=requirements, extra_gt_files=helper)
        (fixture.candidate / "report.html").write_text(html, encoding="utf-8")
        entries, digest = RUNTIME._inventory_tree(fixture.candidate)
        artifact = fixture.candidate.parent / "candidate-artifact.json"
        value = json.loads(artifact.read_text(encoding="utf-8"));value.update(entries=entries, expected_sha256=digest);artifact.write_text(json.dumps(value), encoding="utf-8")
        value = json.loads(fixture.execution_record.read_text(encoding="utf-8"));value["candidate"]["frozen_sha256"] = digest;fixture.execution_record.write_text(json.dumps(value), encoding="utf-8")
        combined = self.root / "combined.json"
        value = json.loads(LOCK_PATH.read_text(encoding="utf-8"));value["html_runtime"] = self.lock
        if office:
            from src.wildclawbench_grading_core.office_runtime import create_office_lock
            binary = self.root / 'office-fixture'
            binary.write_text('#!' + sys.executable + '\nprint("LibreOffice 99.0 fixture")\n', encoding='utf-8')
            binary.chmod(0o755)
            value['office_runtime'] = create_office_lock(binary)
        combined.write_text(json.dumps(value), encoding="utf-8")
        prepared = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package, task_id=fixture.task_id, scoring_attempt_id="html-worker",
            output_root=fixture.output_root, runtime_lock_path=combined)
        return Path(prepared["attempt_root"])

    @unittest.skipIf(os.name == "nt", "Unix process-tree cancellation acceptance")
    def test_outer_worker_cancellation_cleans_separate_browser_session(self):
        rule = '''def grade(**kwargs):
    import os,json,runpy
    from pathlib import Path
    root=Path(kwargs['workspace_path'])
    lock=json.loads(Path(os.environ['GENERAL_E2E_HTML_LOCK']).read_text(encoding='utf-8'))
    api=runpy.run_path(str(root/'gt/html_runtime.py'))
    api['observe_html'](root/'report.html',lock,Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])/'html',timeout_seconds=60)
    return {'html':1.0,'overall_score':1.0}
'''
        attempt = self.worker_attempt(rule, html='<script>while(true){}</script>')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'RULE_WORKER_TIMEOUT'):
            RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=5)
        info = json.loads((attempt / 'worker/derived/html/process-info.json').read_text(encoding='utf-8'))
        deadline = time.monotonic() + 5
        statuses = []
        while time.monotonic() < deadline:
            statuses = [subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True).stdout.strip() for pid in info.values()]
            if all(not s or s.startswith('Z') for s in statuses):
                break
            time.sleep(.1)
        self.assertTrue(all(not s or s.startswith('Z') for s in statuses), statuses)
        self.assertFalse((attempt / 'score.json').exists())

    @unittest.skipIf(os.name == "nt", "Unix fake Office identity fixture")
    def test_combined_office_and_html_preserves_one_derived_inventory_and_zero_score(self):
        rule = """def grade(**kwargs):
    import os,json,runpy
    from pathlib import Path
    root=Path(kwargs['workspace_path'])
    lock=json.loads(Path(os.environ['GENERAL_E2E_HTML_LOCK']).read_text(encoding='utf-8'))
    runpy.run_path(str(root/'gt/html_runtime.py'))['observe_html'](root/'report.html',lock,Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])/'html')
    return {'html':0.0,'overall_score':0.0}
"""
        attempt = self.worker_attempt(rule, office=True)
        RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=40)
        rows = RUNTIME._verify_rule_derived_evidence(attempt, {'office': True, 'html_render': True})
        self.assertEqual(len(rows), len({r['path'] for r in rows}))
        self.assertTrue({'worker/html-runtime.json', 'worker/office-runtime.json'} <= {r['path'] for r in rows})
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        result = RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.assertEqual(result['score']['result']['total_score'], 0.0)
        self.assertTrue(RUNTIME.verify_score_attempt(attempt, archived=True)['score_valid'])

    def test_unfrozen_html_cannot_become_a_verified_source(self):
        rule = """def grade(**kwargs):
    import os,json,runpy
    from pathlib import Path
    root=Path(kwargs['workspace_path'])
    lock=json.loads(Path(os.environ['GENERAL_E2E_HTML_LOCK']).read_text(encoding='utf-8'))
    source=root/'generated.html';source.write_text('<p>invented evidence</p>',encoding='utf-8')
    runpy.run_path(str(root/'gt/html_runtime.py'))['observe_html'](source,lock,Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])/'html')
    return {'html':1.0,'overall_score':1.0}
"""
        attempt = self.worker_attempt(rule)
        RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=40)
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, 'HTML_AUDIT_INVALID'):
            RUNTIME._verify_html_rule_evidence(attempt, required=True)


if __name__ == "__main__":
    unittest.main()
