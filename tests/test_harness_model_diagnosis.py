import importlib.util
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "tools/report/skills/harness-model-diagnosis/scripts"
LEGACY = REPO / "tools/report/skills/entity-eval-diagnosis/scripts/build_entity_profile.py"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


PROFILE = module("build_diagnosis_profile", SCRIPTS / "build_diagnosis_profile.py")
ANALYSIS = module("analyze_diagnosis", SCRIPTS / "analyze_diagnosis.py")
REPORT = module("render_diagnosis_report", SCRIPTS / "render_diagnosis_report.py")


def row(task="a", harness="acode", *, score=1, elapsed=10, total=120, requests=2, run="run1", model="model"):
    usage = dict(input_tokens=total-20, output_tokens=20, total_tokens=total,
                 cache_read_tokens=0, cache_write_tokens=0, elapsed_time=elapsed, request_count=requests)
    return dict(task_id=task, unit=f"{model}@{harness}", harness=harness, model=model,
                run_id=run, run_dir=f"/test/{harness}/{task}/{run}", key=f"{harness}/{task}/{run}",
                score=score, usable=True, validity="PASS", tokens=PROFILE.token_components(usage), usage=usage,
                provenance={k:"digest" for k in PROFILE.CONTRACT_FIELDS},
                execution={"status":"finished", "harness_version":"1.2"}, anomaly_items=[],
                source_sha256={}, sources={})


def profile(rows):
    return {"target_harness":"acode", "target_model":"model", "records":rows}


class HarnessModelProfileTests(unittest.TestCase):
    def test_cache_accounting(self):
        common = dict(output_tokens=20, total_tokens=120, cache_read_tokens=70, cache_write_tokens=10)
        inclusive = PROFILE.token_components(dict(common, input_tokens=100))
        exclusive = PROFILE.token_components(dict(common, input_tokens=20))
        for result in (inclusive, exclusive):
            self.assertEqual(result["input_including_cache"], 100)
            self.assertEqual(result["uncached_input"], 20)
        self.assertNotEqual(inclusive["mode"], exclusive["mode"])

    def test_unknown_is_not_zero(self):
        self.assertEqual(PROFILE.token_components({})["status"], "unavailable")
        usage = dict(input_tokens=10, output_tokens=5, total_tokens=15, cache_read_tokens=0, cache_write_tokens=0)
        self.assertEqual(PROFILE.token_components(dict(usage, usage_complete=False))["status"], "unavailable")
        self.assertEqual(PROFILE.token_components(dict(usage, input_tokens=-1))["status"], "unavailable")
        self.assertEqual(PROFILE.token_components(dict(usage, total_tokens=999))["status"], "inconsistent")

    def test_contract_requires_complete_evidence(self):
        row = {"provenance": {k: "digest" for k in PROFILE.CONTRACT_FIELDS}}
        self.assertEqual(PROFILE.contract_state([row, row]), "same")
        self.assertEqual(PROFILE.contract_state([row, {}]), "unknown")
        self.assertEqual(PROFILE.contract_state([row]), "unknown")
        changed = {"provenance": dict(row["provenance"], task_sha256="changed")}
        self.assertEqual(PROFILE.contract_state([row, changed]), "different")

    def test_score_task_weighting_and_invalid_exclusion(self):
        def row(task, score, usable=True):
            return dict(task_id=task, score=score, usable=usable, tokens={"status": "unavailable"},
                        usage={}, execution={}, anomaly_items=[])
        result = PROFILE.summarize([row("a", 1), row("a", 1), row("b", 0), row("c", 1, False)])
        self.assertEqual(result["mean_score_pct"], 50)
        self.assertEqual(result["scored_tasks"], 2)
        self.assertEqual(result["tokens"]["coverage_runs"], 0)
        self.assertIsNone(result["tokens"]["cache_hit_rate"])

    def test_target_union_and_version_isolation(self):
        def record(model, harness, version, run):
            return SimpleNamespace(model=model, harness=harness, unit=f"{model}@{harness}",
                                   task_id="task", category="category", run_name=run,
                                   run_dir=Path("/nonexistent-entity-profile-test") / run,
                                   score=1, usable=True, validity="PASS", execution={"harness_version": version},
                                   usage={}, anomalies={"items": []}, score_data={})
        records = [record("target-model", "target-harness", "v1", "a"),
                   record("target-model", "target-harness", "v2", "b"),
                   record("target-model", "peer-harness", "v1", "c"),
                   record("peer-model", "target-harness", "v1", "d"),
                   record("irrelevant-model", "irrelevant-harness", "v1", "e")]
        with patch.object(PROFILE, "discover_results", return_value=SimpleNamespace(records=records, issues=[])), \
             patch.object(PROFILE, "parse_report_tool_metrics", return_value={}):
            result = PROFILE.build_profile(Path("/nonexistent-entity-profile-test"), "target-model", "target-harness")
        self.assertEqual(result["scope"]["effective_runs"], 4)
        self.assertEqual(set(result["units"]), {"target-model@target-harness[v1]", "target-model@target-harness[v2]",
                                              "target-model@peer-harness", "peer-model@target-harness"})

    def test_matrix_and_union_have_distinct_scopes(self):
        records = [SimpleNamespace(model=m, harness=h, unit=f"{m}@{h}",task_id="task",category="cat",
                                   run_name=f"{m}-{h}",run_dir=Path("/nonexistent-diagnosis")/m/h,
                                   score=1,usable=True,validity="PASS",execution={"harness_version":"v1"},
                                   usage={},anomalies={},score_data={})
                   for m in ("m1","m2","m3") for h in ("h1","h2","h3")]
        with patch.object(PROFILE,"discover_results",return_value=SimpleNamespace(records=records,issues=[])), \
             patch.object(PROFILE,"parse_report_tool_metrics",return_value={}):
            union = PROFILE.build_profile(Path("/nonexistent-diagnosis"),"m1","h1")
            matrix = PROFILE.build_profile(Path("/nonexistent-diagnosis"),"m1","h1",evidence_scope="selected-matrix",
                                           models=["m1","m2","m3"],harnesses=["h1","h2","h3","missing"])
        self.assertEqual(len(union["units"]),5)
        self.assertEqual(len(matrix["units"]),9)
        self.assertEqual(matrix["scope"]["missing_matrix_cells"],["m1@missing","m2@missing","m3@missing"])
        self.assertEqual(matrix["records"][0]["run_id"],"m1-h1")
        self.assertEqual(matrix["contracts"]["task"]["state"],"unknown")

    def test_scope_requires_explicit_filters_and_targets(self):
        for kwargs in ({}, {"target_model":"m", "evidence_scope":"selected-matrix"},
                       {"target_model":"m", "models":["m"]}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                PROFILE.build_profile(Path("/unused"), **kwargs)

    def test_invalid_resource_values_do_not_become_zero(self):
        for invalid in (None, -1, float("nan"), float("inf"), True, 1.5):
            with self.subTest(value=invalid):
                result = PROFILE.aggregate([10,invalid],integer=True)
                self.assertEqual(result["status"],"partial")
                self.assertIsNone(result["value"])
                self.assertEqual(result["known_subtotal"],10)
                self.assertEqual(result["coverage_runs"],1)
                self.assertEqual(PROFILE.token_components(dict(row()["usage"],input_tokens=invalid))["status"],"unavailable")

    def test_unavailable_partial_and_real_zero_totals(self):
        self.assertIsNone(PROFILE.aggregate([None])["known_subtotal"])
        self.assertIsNone(PROFILE.aggregate([])["value"])
        self.assertEqual(PROFILE.aggregate([0])["value"],0)
        good, bad = row(),row(task="b",requests=None,elapsed=-1)
        bad["tokens"] = {"status":"unavailable"}
        summary = PROFILE.summarize([good,bad])
        self.assertIsNone(summary["tokens"]["total"])
        self.assertEqual(summary["tokens"]["known_subtotals"]["total"],120)
        self.assertIsNone(summary["requests"])
        self.assertIsNone(summary["elapsed_seconds_sum"])
        self.assertEqual(summary["resource_coverage"]["elapsed"]["known_subtotal"],10)

    def test_cache_ratio_is_weighted_and_reasoning_not_added(self):
        a,b = row(),row(task="b",total=220)
        a["usage"]["cache_read_tokens"] = 50
        b["usage"]["cache_read_tokens"] = 150
        for r in (a,b):
            r["usage"]["reasoning_tokens"] = 10
            r["tokens"] = PROFILE.token_components(r["usage"])
        s = PROFILE.summarize([a,b])
        self.assertEqual(s["tokens"]["total"],340)
        self.assertAlmostEqual(s["tokens"]["cache_hit_rate"],200/300)

    def test_json_overwrite_guard_and_nonfinite_serialization(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"profile.json"
            PROFILE.write_json(path,{"bad":float("nan"),"zero":0})
            self.assertEqual(PROFILE.load(path),{"bad":None,"zero":0})
            with self.assertRaises(ValueError):
                PROFILE.write_json(path,{})
            PROFILE.write_json(path,{"new":1},overwrite=True)
            self.assertEqual(PROFILE.load(path),{"new":1})

    def test_usable_score_does_not_erase_review_verdict(self):
        r=row()
        r["anomaly_verdict"]="REVIEW"
        s=PROFILE.summarize([r])
        self.assertEqual(s["scored_tasks"],1)
        self.assertEqual(s["anomaly_verdicts"],{"REVIEW":1})
        md=REPORT.render(profile([r]),ANALYSIS.analyze(profile([r])),[])
        self.assertIn("REVIEW",md)

    def test_optional_source_snapshot_does_not_claim_runtime_proof(self):
        self.assertIsNone(PROFILE.source_snapshot(None))
        with tempfile.TemporaryDirectory() as temp:
            snap=PROFILE.source_snapshot(temp)
        self.assertFalse(snap["runtime_verified"])
        self.assertEqual(snap["deployment_match"],"unknown")
        self.assertIsNone(snap["commit"])
        with self.assertRaises(ValueError):
            PROFILE.source_snapshot("/nonexistent-diagnosis-source")


class PairedAnalysisTests(unittest.TestCase):
    def test_pair_slices_and_symmetric_exclusion(self):
        rows=[row("a",elapsed=100,total=220),row("a","cc",elapsed=10),
              row("b",score=.5,elapsed=50),row("b","cc",score=.5,elapsed=20),
              row("c",score=.5,elapsed=5),row("c","cc",score=1,elapsed=10)]
        rows[-1]["execution"]["status"]="error"
        rows[-1]["provenance"]={}
        pair=ANALYSIS.analyze(profile(rows),exclude_task_ids=["b"],tail_count=1)["pairs"][0]
        slices=pair["slices"]
        self.assertEqual(slices["all_paired"]["tasks"],3)
        self.assertEqual(slices["same_contract"]["task_ids"],["a","b"])
        self.assertEqual(slices["equal_score"]["task_ids"],["a","b"])
        self.assertEqual(slices["both_perfect"]["task_ids"],["a"])
        self.assertEqual(slices["paired_finished"]["task_ids"],["a","b"])
        self.assertEqual(slices["without_explicit_tasks"]["task_ids"],["a","c"])
        self.assertEqual(slices["without_explicit_tasks"]["target"]["runs"],2)
        self.assertEqual(slices["without_explicit_tasks"]["comparison"]["runs"],2)
        self.assertEqual(pair["tail_selection"]["selected_task_ids"],["a"])
        self.assertEqual(slices["without_elapsed_tails"]["target"]["elapsed_seconds_sum"],55)
        self.assertEqual(slices["without_elapsed_tails"]["comparison"]["elapsed_seconds_sum"],30)
        self.assertEqual(slices["all_paired"]["run_pairs"][0]["target_run_id"],"run1")

    def test_zero_denominator_and_missing_metric_not_comparable(self):
        delta=ANALYSIS.difference({"zero":3,"missing":None},{"zero":0,"missing":10})
        self.assertEqual(delta["zero"]["delta"],3)
        self.assertIsNone(delta["zero"]["relative_pct"])
        self.assertIsNone(delta["missing"]["delta"])
        result=ANALYSIS.analyze(profile([row(requests=None),row(harness="cc")]))
        self.assertIsNone(result["pairs"][0]["slices"]["all_paired"]["changes"]["requests"]["relative_pct"])

    def test_duplicate_runs_not_arbitrarily_paired(self):
        result=ANALYSIS.analyze(profile([row(),row(run="run2"),row(harness="cc"),row("only-a"),row("only-b","cc")]))
        pair=result["pairs"][0]
        self.assertEqual(pair["ambiguous_multi_run_tasks"],["a"])
        self.assertEqual(pair["slices"]["all_paired"]["tasks"],0)
        self.assertEqual(pair["target_only_tasks"],["only-a"])
        self.assertEqual(pair["comparison_only_tasks"],["only-b"])
        self.assertEqual(result["units"]["model@acode"]["runs"],3)

    def test_pair_directions_and_target_unit(self):
        rows=[row(model=m,harness=h) for m in ("model","peer") for h in ("acode","cc")]
        result=ANALYSIS.analyze(profile(rows))
        self.assertEqual(len(result["pairs"]),4)
        for pair in result["pairs"]:
            self.assertNotEqual(pair["target_unit"],pair["comparison_unit"])
            if pair["kind"]=="same_model":
                self.assertTrue(pair["target_unit"].endswith("@acode"))
            else:
                self.assertTrue(pair["target_unit"].startswith("model@"))
        selected=ANALYSIS.analyze(profile(rows),target_unit="model@cc")
        self.assertEqual(len(selected["pairs"]),2)
        self.assertTrue(all(p["target_unit"]=="model@cc" for p in selected["pairs"]))
        with self.assertRaises(ValueError):
            ANALYSIS.analyze(profile(rows),target_unit="absent")

    def test_tail_selection_is_deterministic_positive_and_optional(self):
        rows=[row("z",elapsed=20),row("z","cc",elapsed=10),row("a",elapsed=20),row("a","cc",elapsed=10),
              row("negative",elapsed=1),row("negative","cc",elapsed=50)]
        for data in (rows,list(reversed(rows))):
            p=ANALYSIS.analyze(profile(data),tail_count=1)["pairs"][0]
            self.assertEqual(p["tail_selection"]["selected_task_ids"],["a"])
        p=ANALYSIS.analyze(profile(rows),tail_count=0)["pairs"][0]
        self.assertEqual(p["slices"]["without_elapsed_tails"]["tasks"],3)
        for count in (-1,True,1.5):
            with self.assertRaises(ValueError):
                ANALYSIS.analyze(profile(rows),tail_count=count)

    def test_invalid_scores_cannot_enter_equal_score_slice(self):
        rows=[]
        for task,score in (("over",2),("negative",-1),("bool",True),("nan",float("nan"))):
            rows += [row(task,score=score),row(task,"cc",score=score)]
        rows += [row("invalid"),row("invalid","cc")]
        rows[-1]["usable"]=False
        p=ANALYSIS.analyze(profile(rows))["pairs"][0]
        self.assertEqual(p["slices"]["equal_score"]["tasks"],0)
        self.assertEqual(p["slices"]["all_paired"]["tasks"],5)

    def test_legacy_profile_run_id_derived_and_bad_exclusion_rejected(self):
        a,b=row(),row(harness="cc")
        del a["run_id"]
        pair=ANALYSIS.analyze(profile([a,b]))["pairs"][0]
        self.assertEqual(pair["slices"]["all_paired"]["run_pairs"][0]["target_run_id"],"run1")
        with self.assertRaises(ValueError):
            ANALYSIS.analyze(profile([a,b]),exclude_task_ids=["not-selected"])


class EvidenceAndReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run=Path(self.temp.name)/"actual-run"
        self.run.mkdir()
        self.source=self.run/"agent_interaction.jsonl"
        self.source.write_text('{"event":"schema"}\n{"error":"missing cmd"}\n',encoding="utf-8")
        r=row()
        r.update(run_id=self.run.name,run_dir=str(self.run),sources={"trace":str(self.source)},
                 source_sha256={"trace":PROFILE.fingerprint(self.source)})
        self.p=profile([r])
        self.finding={"id":"M-01","target":{"kind":"model","id":"model"},"title":"参数错误后恢复",
                      "finding_type":"confirmed_problem","layer":"L1b","confidence":"confirmed",
                      "observation":"schema 要求 cmd，模型发出其他字段",
                      "scope":{"affected_tasks":1,"examined_tasks":1,"affected_runs":1,"examined_runs":1},
                      "task_ids":["a"],"impact":{"observed":"一次错误","causal":"工具参数不满足协议","not_proven":"未证明失分"},
                      "evidence":[{"unit":"model@acode","task_id":"a","run_id":self.run.name,
                                   "source":str(self.source),"line":2,"locator":"event 2","excerpt":"missing cmd",
                                   "call_id":"call-1"}],"counterevidence":["此任务满分"],
                      "recommendation":"降低接口歧义","validation":"固定模型和契约复验"}

    def test_valid_runtime_evidence_rendered_with_run_and_version(self):
        findings=REPORT.validate_findings(self.p,{"findings":[self.finding]})
        a=ANALYSIS.analyze(self.p)
        a["verification"]=ANALYSIS.verify_profile(self.p)
        md=REPORT.render(self.p,a,findings,"rd")
        self.assertIn(self.run.name,md)
        self.assertIn("acode 1.2@model",md)
        self.assertIn("call-1",md)
        self.assertIn(f"<{self.source}:2>",md)
        self.assertIn("120",md)
        self.assertIn("未证明失分",md)

    def test_rejects_wrong_run_task_or_external_evidence(self):
        for field,value in (("run_id","wrong"),("unit","model@cc"),("task_id","wrong"),
                            ("source",str(Path(__file__).resolve()))):
            bad=copy.deepcopy(self.finding)
            bad["evidence"][0][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                REPORT.validate_findings(self.p,{"findings":[bad]})

    def test_line_boundaries_and_evidence_shape(self):
        for line in (0,3,True,"2"):
            bad=copy.deepcopy(self.finding)
            bad["evidence"][0]["line"]=line
            with self.subTest(line=line), self.assertRaises(ValueError):
                REPORT.validate_findings(self.p,{"findings":[bad]})
        for field,value in (("task_ids","a"),("counterevidence","none"),("evidence",{}),("scope",None)):
            bad=copy.deepcopy(self.finding)
            bad[field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                REPORT.validate_findings(self.p,{"findings":[bad]})

    def test_source_only_is_not_runtime_proof(self):
        source={"evidence_type":"source_code","source":str(self.source),"locator":"line 1","excerpt":"schema"}
        bad=copy.deepcopy(self.finding)
        bad["evidence"].append(source)
        with self.assertRaises(ValueError):
            REPORT.validate_findings(self.p,{"findings":[bad]})
        source.update(commit="abc123",symbol="register")
        REPORT.validate_findings(self.p,{"findings":[bad]})
        bad["evidence"]=[source]
        with self.assertRaises(ValueError):
            REPORT.validate_findings(self.p,{"findings":[bad]})

    def test_scope_cannot_have_missing_denominators_or_impossible_counts(self):
        for scope in ({}, {"affected_tasks":2,"examined_tasks":1,"affected_runs":2,"examined_runs":2},
                      {"affected_tasks":1,"examined_tasks":True,"affected_runs":1,"examined_runs":1}):
            bad=copy.deepcopy(self.finding)
            bad["scope"]=scope
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                REPORT.validate_findings(self.p,{"findings":[bad]})

    def test_statistics_only_report_retains_missing_data_boundary(self):
        self.p["records"][0]["usage"]["request_count"]=None
        md=REPORT.render(self.p,ANALYSIS.analyze(self.p),[])
        self.assertIn("不可用",md)
        self.assertIn("不是完整根因诊断",md)
        self.assertIn("没有可用对照",md)

    def test_source_fingerprint_drift_blocks_analysis(self):
        self.assertEqual(ANALYSIS.verify_profile(self.p)["verified_files"],1)
        self.source.write_text("changed",encoding="utf-8")
        with self.assertRaises(ValueError):
            ANALYSIS.verify_profile(self.p)
        del self.p["records"][0]["source_sha256"]
        self.assertEqual(ANALYSIS.verify_profile(self.p)["missing_fingerprint_runs"],1)

    def test_cli_pipeline_and_profile_binding(self):
        root=Path(self.temp.name)
        pp,ap,fp,md=root/"p.json",root/"a.json",root/"f.json",root/"r.md"
        PROFILE.write_json(pp,self.p)
        PROFILE.write_json(fp,{"findings":[self.finding]})
        analyze=subprocess.run([sys.executable,"-B",str(SCRIPTS/"analyze_diagnosis.py"),"--profile",str(pp),
                                "--output",str(ap)],capture_output=True,text=True)
        self.assertEqual(analyze.returncode,0,analyze.stderr)
        cmd=[sys.executable,"-B",str(SCRIPTS/"render_diagnosis_report.py"),"--profile",str(pp),"--analysis",str(ap),
             "--findings",str(fp),"--audience","rd","--output",str(md)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn(self.run.name,md.read_text(encoding="utf-8"))
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        PROFILE.write_json(pp,dict(self.p,changed=True),overwrite=True)
        result=subprocess.run(cmd+["--overwrite"],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("fingerprint",result.stderr)

    def test_legacy_cli_and_imports(self):
        legacy=module("legacy_entity_profile",LEGACY)
        self.assertEqual(legacy.summarize([row()])["requests"],2)
        self.assertTrue(callable(legacy.build_profile))
        result=subprocess.run([sys.executable,"-B",str(LEGACY),"--help"],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("--target-harness",result.stdout)


if __name__ == "__main__":
    unittest.main()
