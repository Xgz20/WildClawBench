from __future__ import annotations

import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tests.general_e2e.test_image_evidence import write_image
from tests.general_e2e.test_local_scoring_runtime import Fixture, LOCK_PATH, RUNTIME
from tests.general_e2e.test_general_semantic_scoring import RUBRIC
from tests.general_e2e import test_general_api_judge as api_tests


class ImageSemanticTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="general-image-protocol-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _attempt(self, name, *, provider="openai-responses", image_config=True, overrides=None,
                 invalid=False, prepare=True, base_url=None, count=2):
        fixture = Fixture(self.root / name, rule="", grading_type="llm_judge",
            grading_weights={"automated": 0., "llm_judge": 1.}, llm_judge_rubric=RUBRIC)
        for number in range(count):
            path = fixture.candidate / f"annotated/page-{number+1}.png"
            write_image(path, color="red" if number == 0 else "blue")
            if invalid and number == 0:path.write_bytes(b"not a PNG")
        entries, digest = RUNTIME._inventory_tree(fixture.candidate)
        artifact_path = fixture.candidate.parent / "candidate-artifact.json"
        artifact = json.loads(artifact_path.read_text());artifact.update(entries=entries, expected_sha256=digest)
        artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
        execution = json.loads(fixture.execution_record.read_text());execution["candidate"]["frozen_sha256"] = digest
        fixture.execution_record.write_text(json.dumps(execution), encoding="utf-8")
        config = api_tests.GeneralApiJudgeTests._config(self, fixture.root, provider=provider, max_input_chars=100_000)
        raw = json.loads(config.read_text())
        if base_url:raw["base_url"] = base_url
        if image_config:
            raw["image_input"] = {"max_images": 12, "max_image_bytes": 5_000_000, "max_total_bytes": 20_000_000,
                                  "max_pixels": 16_000_000, "detail": "native" if provider == "anthropic-messages" else "high"}
            raw["image_input"].update(overrides or {})
        config.write_text(json.dumps(raw), encoding="utf-8")
        if not prepare:return config
        result = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package, task_id=fixture.task_id, scoring_attempt_id="score-"+name,
            output_root=fixture.output_root, runtime_lock_path=LOCK_PATH, judge_protocol="api-judge-v1",
            judge_model="fixture-vision", judge_reasoning_effort="high", judge_attempt_id="judge-"+name,
            api_runtime_config_path=config)
        attempt = Path(result["attempt_root"])
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        return attempt

    def _packet(self, attempt):
        return json.loads((attempt / "semantic/api-input.json").read_text())

    def _response(self, attempt, provider, *, unresolved=False):
        candidate = api_tests.GeneralApiJudgeTests._candidate(self, attempt)
        images = self._packet(attempt).get("image_attachments", [])
        for row in candidate["criteria"]:
            if images:row["evidence_ids"] = [images[0]["evidence_id"]]
            if unresolved:row.update(status="unresolved", score=None, reason="图片证据缺失或无法确认关键区域，不能从元数据补出业务判定。")
        if provider == "anthropic-messages":return api_tests.GeneralApiJudgeTests._anthropic_response(candidate)
        if provider == "openai-responses":return api_tests.GeneralApiJudgeTests._responses_api_response(candidate)
        return api_tests.GeneralApiJudgeTests._openai_response(json.dumps(candidate), "chat-image-fixture")

    def test_three_provider_bodies_send_exact_labeled_pixels(self):
        for provider in ("anthropic-messages", "openai-chat-completions", "openai-responses"):
            with self.subTest(provider=provider):
                attempt = self._attempt(provider, provider=provider)
                packet = self._packet(attempt);judge = json.loads((attempt/"private/judge-config.json").read_text())
                catalog = json.loads((attempt/"semantic/evidence-catalog.json").read_text())
                RUNTIME._validate_api_image_bindings(attempt, packet, catalog, judge, decode_images=True)
                body, _ = RUNTIME._api_request_document(packet, judge)
                content = body["input"][-1]["content"] if provider == "openai-responses" else body["messages"][-1]["content"]
                blocks = [item for item in content if item["type"] in {"image", "input_image", "image_url"}]
                self.assertEqual(len(blocks), 2)
                for index, block in enumerate(blocks):
                    if provider == "anthropic-messages":encoded = block["source"]["data"]
                    else:
                        value = block["image_url"] if provider == "openai-responses" else block["image_url"]["url"]
                        encoded = value.split(",", 1)[1]
                    raw = base64.b64decode(encoded)
                    image = packet["image_attachments"][index]
                    self.assertEqual(raw, (attempt/image["path"]).read_bytes())
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), image["source_sha256"])
                    self.assertTrue(any(image["evidence_id"] in item.get("text", "") for item in content))

    def test_legacy_config_keeps_text_only_packet_and_body(self):
        attempt = self._attempt("disabled", image_config=False)
        packet = self._packet(attempt);self.assertNotIn("image_attachments", packet)
        judge = json.loads((attempt/"private/judge-config.json").read_text())
        body, _ = RUNTIME._api_request_document(packet, judge)
        self.assertIsInstance(body["input"][-1]["content"], str)
        rows = json.loads(packet["user_prompt"])["evidence"]
        self.assertTrue(all(row["evidence_id"] not in packet["packet_summary"]["usable_evidence_ids"] for row in rows if row.get("path", "").endswith(".png")))

    def test_count_byte_pixel_budgets_and_invalid_images_are_not_usable(self):
        scenarios = [("count", {"max_images": 1}, False, "image_omitted_budget"),
                     ("bytes", {"max_total_bytes": 200, "max_image_bytes": 200}, False, "image_omitted_budget"),
                     ("pixels", {"max_pixels": 100}, False, "image_unavailable"),
                     ("invalid", {}, True, "image_unavailable")]
        for name, limits, invalid, expected in scenarios:
            with self.subTest(name=name):
                attempt = self._attempt(name, overrides=limits, invalid=invalid)
                packet = self._packet(attempt);rows = json.loads(packet["user_prompt"])["evidence"]
                omitted = [row for row in rows if row["content_status"] == expected]
                self.assertTrue(omitted)
                self.assertTrue(all(row["evidence_id"] not in packet["packet_summary"]["usable_evidence_ids"] for row in omitted))
                self.assertLessEqual(packet["packet_summary"]["image_bytes"], limits.get("max_total_bytes", 20_000_000))

    def test_image_config_rejects_unknown_unsafe_or_provider_incompatible_values(self):
        for index, values in enumerate([{"max_images": True}, {"detail": []}, {"max_pixels": 0},
                                        {"max_images": 21}, {"unknown": 1}, {"max_total_bytes": 1}]):
            config = self._attempt("bad-config-"+str(index), overrides=values, prepare=False)
            with self.subTest(values=values), self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._load_api_runtime_config(config)
        config = self._attempt("bad-anthropic-detail", provider="anthropic-messages", overrides={"detail":"high"}, prepare=False)
        with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._load_api_runtime_config(config)

    def test_rehashed_packet_with_wrong_or_missing_pixels_still_fails_frozen_binding(self):
        attempt = self._attempt("tamper");packet = self._packet(attempt)
        judge = json.loads((attempt/"private/judge-config.json").read_text());catalog=json.loads((attempt/"semantic/evidence-catalog.json").read_text())
        for mode in ("swap", "missing", "duplicate", "path", "metadata"):
            value=copy.deepcopy(packet)
            if mode=="swap":value["image_attachments"][0]["data_base64"]=value["image_attachments"][1]["data_base64"]
            elif mode=="missing":value["image_attachments"].pop()
            elif mode=="duplicate":value["image_attachments"][1]=copy.deepcopy(value["image_attachments"][0])
            elif mode=="path":value["image_attachments"][0]["path"]="../outside.png"
            else:value["image_attachments"][0]["width"]=65
            with self.subTest(mode=mode), self.assertRaises(RUNTIME.ScoringRuntimeError):
                RUNTIME._validate_api_image_bindings(attempt,value,catalog,judge,decode_images=True)

    def test_omitted_image_citation_fails(self):
        attempt=self._attempt("omitted-citation",overrides={"max_images":1})
        packet=self._packet(attempt);rows=json.loads(packet["user_prompt"])["evidence"]
        omitted=next(row["evidence_id"] for row in rows if row["content_status"]=="image_omitted_budget")
        candidate=api_tests.GeneralApiJudgeTests._candidate(self,attempt)
        for row in candidate["criteria"]:row["evidence_ids"]=[omitted]
        with patch.dict(os.environ,{"GENERAL_E2E_TEST_API_KEY":"fixture"}), patch.object(RUNTIME,"_api_http_exchange",
             return_value=api_tests.GeneralApiJudgeTests._responses_api_response(candidate)):
            result=RUNTIME.run_api_score_attempt(attempt_root=attempt)
        self.assertFalse(result["score_valid"])
        self.assertIsNone(json.loads((attempt/"score.json").read_text())["result"]["total_score"])

    def test_missing_decoder_before_send_stays_infrastructure_failure(self):
        attempt=self._attempt("missing-decoder")
        with patch.object(RUNTIME,"_image_evidence",side_effect=RUNTIME.ScoringRuntimeError("IMAGE_EVIDENCE_DEPENDENCY_MISSING","Pillow")), patch.object(RUNTIME,"_api_http_exchange") as exchange:
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,"IMAGE_EVIDENCE_DEPENDENCY_MISSING"):
                RUNTIME.run_api_judge_attempt(attempt_root=attempt)
        exchange.assert_not_called()
        self.assertFalse((attempt/"score.json").exists())

    def test_unresolved_image_stays_null_not_zero(self):
        attempt=self._attempt("unresolved-image")
        with patch.dict(os.environ,{"GENERAL_E2E_TEST_API_KEY":"fixture"}), patch.object(RUNTIME,"_api_http_exchange",
             return_value=self._response(attempt,"openai-responses",unresolved=True)):
            result=RUNTIME.run_api_score_attempt(attempt_root=attempt)
        self.assertFalse(result["score_valid"])
        self.assertIsNone(json.loads((attempt/"score.json").read_text())["result"]["total_score"])

    def test_recorded_provider_body_cannot_swap_images_even_after_rehashing_audits(self):
        attempt=self._attempt("body-tamper")
        with patch.dict(os.environ,{"GENERAL_E2E_TEST_API_KEY":"fixture"}), patch.object(RUNTIME,"_api_http_exchange",
             return_value=self._response(attempt,"openai-responses")):
            RUNTIME.run_api_score_attempt(attempt_root=attempt)
        api_path=attempt/"semantic/api-audit.json";api=json.loads(api_path.read_text())
        sent_path=attempt/api["attempts"][0]["request_path"];sent=json.loads(sent_path.read_text())
        blocks=sent["body"]["input"][-1]["content"];images=[b for b in blocks if b["type"]=="input_image"]
        images[0]["image_url"]=images[1]["image_url"]
        sent["body_sha256"]=RUNTIME._sha256_bytes(RUNTIME._canonical_json_bytes(sent["body"]))
        sent_path.write_text(json.dumps(sent),encoding="utf-8")
        api["attempts"][0]["request_sha256"]=RUNTIME._sha256_file(sent_path)
        api_path.write_text(json.dumps(api),encoding="utf-8")
        audit_path=RUNTIME._semantic_paths(attempt)["audit"];audit=json.loads(audit_path.read_text())
        audit["api_audit_sha256"]=RUNTIME._sha256_file(api_path);audit_path.write_text(json.dumps(audit),encoding="utf-8")
        manifest=json.loads((attempt/"attempt-manifest.json").read_text())
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,"API_JUDGE_IMAGE_BINDING_INVALID"):
            RUNTIME._verify_semantic_terminal(attempt,manifest)

    def test_actual_loopback_http_for_all_providers_and_archived_verification(self):
        captured=[];response_data=[None]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                raw=response_data[0];self.send_response(200);self.send_header("Content-Type","application/json");self.end_headers();self.wfile.write(raw)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for provider in ("anthropic-messages","openai-chat-completions","openai-responses"):
                attempt=self._attempt("http-"+provider,provider=provider,base_url=f"http://127.0.0.1:{server.server_port}")
                _,_,raw=self._response(attempt,provider);response_data[0]=raw
                with patch.dict(os.environ,{"GENERAL_E2E_TEST_API_KEY":"local-fixture-no-live-credential"}):
                    result=RUNTIME.run_api_score_attempt(attempt_root=attempt)
                self.assertTrue(result["score_valid"])
                self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)["score_valid"])
                self.assertEqual(len(captured),len(list(self.root.glob('http-*'))))
                body=captured[-1];content=body["input"][-1]["content"] if provider=="openai-responses" else body["messages"][-1]["content"]
                self.assertEqual(sum(row["type"] in {"image","image_url","input_image"} for row in content),2)
                # Archive checking needs original bytes, not Pillow or network access.
                with patch.object(RUNTIME,"_image_evidence",side_effect=AssertionError("decoder must not be needed")):
                    self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)["score_valid"])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


class CodexImageQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def _attempt(self,name):
        fixture=Fixture(self.root/name,rule="",grading_type="llm_judge",grading_weights={"automated":0.,"llm_judge":1.},llm_judge_rubric=RUBRIC)
        write_image(fixture.candidate/"annotated/source.png")
        entries,digest=RUNTIME._inventory_tree(fixture.candidate)
        path=fixture.candidate.parent/"candidate-artifact.json";value=json.loads(path.read_text());value.update(entries=entries,expected_sha256=digest);path.write_text(json.dumps(value),encoding="utf-8")
        value=json.loads(fixture.execution_record.read_text());value["candidate"]["frozen_sha256"]=digest;fixture.execution_record.write_text(json.dumps(value),encoding="utf-8")
        attempt=fixture.prepare("score-"+name);RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        page=RUNTIME.query_evidence_attempt(attempt_root=attempt,mode="catalog",path_contains="source.png")
        return attempt,page["items"][0]["id"],page["query_id"]

    def test_query_returns_verified_path_and_metadata_without_claiming_pixel_inspection(self):
        attempt,identity,_=self._attempt("query")
        before=RUNTIME._inventory_tree(attempt/"candidate-original/workspace")[1]
        result=RUNTIME.query_evidence_attempt(attempt_root=attempt,mode="image",evidence_id=identity)
        item=result["items"][0];path=Path(item["view_image_path"])
        self.assertEqual(RUNTIME._sha256_file(path),item["source_sha256"])
        self.assertEqual((item["width"],item["height"]),(64,48));self.assertTrue(item["pixel_inspection_required"])
        self.assertNotIn("data_base64",item);self.assertFalse(result["has_more"])
        log=json.loads((attempt/"semantic/query-log.json").read_text())["queries"][-1]
        self.assertEqual(log["coverage"]["kind"],"image-bytes")
        self.assertEqual(log["coverage"]["image"]["source_sha256"],item["source_sha256"])
        self.assertEqual(before,RUNTIME._inventory_tree(attempt/"candidate-original/workspace")[1])
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,"SEMANTIC_QUERY_PAGE_INVALID"):
            RUNTIME.query_evidence_attempt(attempt_root=attempt,mode="image",evidence_id=identity,offset=1)

    def test_metadata_catalog_alone_cannot_authorize_a_judged_image_citation(self):
        for image_query in (False,True):
            attempt,identity,catalog_query=self._attempt("cite-"+str(image_query))
            query=RUNTIME.query_evidence_attempt(attempt_root=attempt,mode="image",evidence_id=identity)["query_id"] if image_query else catalog_query
            template=json.loads((attempt/"semantic/response-template.json").read_text())
            for row in template["criteria"]:
                row.update(status="judged",score=1.,reason="测试夹具只验证图片引用协议，不构成真实视觉或语义判断。",evidence_ids=[identity],
                    review={"query_ids":[query],"supporting_evidence_checked":True,"contradicting_evidence_checked":True,"absence_claim":False,"complete_event_range_checked":False})
            path=attempt/"response-input.json";path.write_text(json.dumps(template),encoding="utf-8")
            if image_query:
                result=RUNTIME.record_semantics_attempt(attempt_root=attempt,response_path=path)
                self.assertEqual(result["semantic_component"]["status"],"completed")
            else:
                with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,"SEMANTIC_IMAGE_QUERY_REQUIRED"):
                    RUNTIME.record_semantics_attempt(attempt_root=attempt,response_path=path)
                audit=json.loads(RUNTIME._semantic_paths(attempt)["audit"].read_text())
                self.assertEqual(audit["error"]["code"],"SEMANTIC_IMAGE_QUERY_REQUIRED")


if __name__ == "__main__":unittest.main()
