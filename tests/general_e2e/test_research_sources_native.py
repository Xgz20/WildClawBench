"""Offline mechanism fixtures: no network, Office, model or task-scientific oracle."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tests.general_e2e.test_local_scoring_runtime import Fixture, RUNTIME, REPO_ROOT, load_module
import native_source_projection as N
import research_source_dispatch as D
import research_sources_native as V2

V1 = RUNTIME.research_sources
V1_SHA = "4fcb5239474bf5d3749f817abdccd02054ba86e2d766458f78f70d2da8c8968a"
POLICY = {"schema_version":V2.POLICY_SCHEMA,"projection_profile":N.PROFILE,
          "ledger_path":"results/sources.json","deliverable_paths":["results/sources.json"],
          "as_of_inclusive":"2026-09-30","timezone":"Asia/Shanghai"}
SPEC = {**V2.POLICY_DEFAULTS,**POLICY}
MIME = {"docx":"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx":"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
RULE = '''
def grade(transcript, workspace_path):
    import json
    import os
    from pathlib import Path
    bundle = Path(os.environ['GENERAL_E2E_RESEARCH_SOURCE_BUNDLE'])
    manifest = json.loads((bundle/'manifest.json').read_text())
    row = manifest['sources'][0]
    projection = json.loads((bundle/row['projection_path']).read_text())
    ok = projection['complete'] and projection['source_sha256'] == row['body_sha256']
    return {'fixture':float(ok),'overall_score':float(ok)}
'''.strip()
RUBRIC = "### Criterion 1: 机制证据 (key: fixture, weight: 1.0)\n**Score 1.0**: 绑定可查。\n**Score 0.0**: 缺失。"


def package(kind="docx", *, extra=None, body=None):
    main = "word/document.xml" if kind=="docx" else "xl/workbook.xml"
    entries = {
        "[Content_Types].xml":f'<Types xmlns="{N.CT[1:-1]}"><Override PartName="/{main}" ContentType="{N.MAIN_TYPES[kind]}"/></Types>',
        "_rels/.rels":f'<Relationships xmlns="{N.PKG_REL[1:-1]}"><Relationship Id="main" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="{main}"/></Relationships>',
    }
    if kind=="docx":
        entries[main]=body or f'<w:document xmlns:w="{N.W[1:-1]}"><w:body><w:p><w:r><w:t>independent publication</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>原生单元格</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
    else:
        entries.update({
            main:f'<workbook xmlns="{N.S[1:-1]}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="原表" sheetId="1" state="hidden" r:id="sheet"/></sheets><definedNames><definedName name="区域">原表!$A$1:$D$1</definedName></definedNames></workbook>',
            "xl/_rels/workbook.xml.rels":f'<Relationships xmlns="{N.PKG_REL[1:-1]}"><Relationship Id="sheet" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="outside" Type="hyperlink" TargetMode="External" Target="https://external.example/never-follow"/></Relationships>',
            "xl/worksheets/sheet1.xml":body or f'<worksheet xmlns="{N.S[1:-1]}"><cols><col min="1" max="1" hidden="1"/></cols><sheetData><row r="1" hidden="1"><c r="A1" t="inlineStr"><is><t>independent publication</t></is></c><c r="B1"><f>1+1</f><v>2</v></c><c r="C1"><f>1/0</f></c><c r="D1" t="str"><f>IF(1,&quot;&quot;)</f><v/></c><c r="E1"><v>0</v></c><c r="F1" t="b"><v>0</v></c></row></sheetData><mergeCells><mergeCell ref="A2:B2"/></mergeCells></worksheet>',
        })
    entries.update(extra or {})
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name,value in entries.items():archive.writestr(name,value)
    return out.getvalue()


def public_fetch(payload, media):
    def fetch(url,destination,specification,curl=None):
        destination.write_bytes(payload)
        return {"requested_url":url,"final_url":url,"http_status":200,"redirect_count":0,
                "responses":[{"url":url,"status":200,"headers":{"content-type":media},"validated_addresses":["8.8.8.8"],"connected_address":"8.8.8.8"}],
                "public_address_policy":"global-unicast-dns-pinned-no-proxy/v1","media_type":media,
                "started_at":"2026-10-28T01:00:00Z","finished_at":"2026-10-28T01:00:01Z",
                "tls_verification":"curl-default-no-insecure","fetcher":{"name":"curl","version":"fixture","path":"/fixture/never-executed","sha256":"a"*64},
                "body_sha256":V1.sha(destination),"body_size":len(payload)}
    return fetch


class NativeSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="native-source-mechanism-")
        self.root=Path(self.temp.name)

    def tearDown(self):
        for path in self.root.rglob("*"):
            if not path.is_symlink():path.chmod(0o755 if path.is_dir() else 0o644)
        self.temp.cleanup()

    def original(self,kind="docx",payload=None):
        p=self.root/("original."+kind);p.write_bytes(payload or package(kind));return p

    def fixture(self,name="task",kind="docx",*,v1=False,hybrid=False,quote="independent publication"):
        policy={**POLICY}
        if v1:
            policy.pop("projection_profile");policy["schema_version"]=V1.POLICY_SCHEMA
        f=Fixture(self.root/name,rule=RULE,scoring_runtime={"research_sources":True},
                  extra_gt_files={V1.POLICY_PATH:V1.encoded(policy)},
                  grading_type="hybrid" if hybrid else "automated",
                  grading_weights={"automated":.5,"llm_judge":.5} if hybrid else {},llm_judge_rubric=RUBRIC if hybrid else "")
        (f.candidate/"results").mkdir()
        ledger={"sources":[{"source_id":"source","url":"https://publication.example/original."+("html" if v1 else kind),
                             "access_status":"read_full","citations":[{"citation_id":"q","quote":quote,"locator":{"node":"paragraph:1"}}]}]}
        (f.candidate/"results/sources.json").write_text(json.dumps(ledger))
        entries,digest=RUNTIME._inventory_tree(f.candidate)
        ap=f.candidate.parent/"candidate-artifact.json"; artifact=json.loads(ap.read_text());artifact.update(entries=entries,expected_sha256=digest);ap.write_text(json.dumps(artifact))
        execution=json.loads(f.execution_record.read_text());execution['candidate']['frozen_sha256']=digest;f.execution_record.write_text(json.dumps(execution))
        # A test-only standard-library worker based solely on the current bundled
        # interpreter. No dependencies are installed or Office assets provisioned.
        lock=V1.read(Path(RUNTIME.__file__).resolve().parents[1]/"references/scoring-runtime-lock.json")
        lock.update(python={"major":sys.version_info.major,"minor":sys.version_info.minor},dependencies=[])
        lp=self.root/(name+"-runtime-lock.json");lp.write_bytes(V1.encoded(lock))
        return Path(RUNTIME.prepare_attempt(unit_root=f.unit_root,execution_record_path=f.execution_record,
            scoring_package=f.scoring_package,task_id=f.task_id,scoring_attempt_id="score-"+name,
            output_root=f.output_root,runtime_lock_path=lp,
            **({"judge_protocol":"codex-agent-judge-v1","judge_model":"mechanism-fixture","judge_reasoning_effort":"high","judge_attempt_id":"judge-"+name} if hybrid else {}))["attempt_root"])

    def collect(self,attempt,kind="docx",*,v1=False,origins=()):
        module=V1 if v1 else V2
        payload=b'<html><p>independent publication</p></html>' if v1 else package(kind)
        media="text/html" if v1 else MIME[kind]
        with patch.object(module,"fetch",side_effect=public_fetch(payload,media)), patch("socket.getaddrinfo",side_effect=AssertionError("network forbidden")):
            return RUNTIME.collect_research_sources_attempt(attempt_root=attempt,reuse_sources_from=origins)

    def worker(self,attempt):
        venv=self.root/"stdlib-worker"
        if not venv.exists():subprocess.run([sys.executable,"-m","venv","--without-pip",str(venv)],check=True,capture_output=True)
        python=venv/("Scripts/python.exe" if os.name=="nt" else "bin/python")
        return RUNTIME.run_rules_attempt(attempt_root=attempt,runtime_python=python,timeout_seconds=20)

    def finish(self,attempt):
        self.worker(attempt);RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.assertTrue(RUNTIME.verify_score_attempt(attempt)["score_valid"])

    def test_original_collector_pin_and_private_dispatch_preserved(self):
        self.assertEqual(V1.sha(Path(V1.__file__)),V1_SHA)
        old=self.fixture("old",v1=True);new=self.fixture("new")
        self.assertIs(D.backend(old),V1);self.assertIs(D.backend(new),V2)
        before=V1.sha(old/"attempt-manifest.json")
        self.collect(old,v1=True)
        self.assertEqual(V1.sha(old/"attempt-manifest.json"),before)
        doc=V1.read(old/V1.BUNDLE_PATH/"manifest.json")
        self.assertEqual(doc["schema_version"],V1.BUNDLE_SCHEMA)
        self.assertEqual(doc["collector_sha256"],V1_SHA)
        self.assertNotIn("projection_profile",doc["policy"])
        self.assertEqual(D.verify(old,required=True,attempt_verifier=RUNTIME.verify_attempt),V1.verify(old,required=True,attempt_verifier=RUNTIME.verify_attempt))

    def test_docx_native_nodes_original_and_engine_identity(self):
        p=self.original(); projection=N.project(p,MIME['docx'],SPEC)
        self.assertEqual(projection['source_sha256'],V1.sha(p));self.assertTrue(projection['complete'])
        self.assertEqual(projection['records'][0]['locator']['node'],'paragraph:1')
        self.assertEqual(projection['records'][1]['native']['locator'],'table:1/row:1/cell:1')
        self.assertTrue(projection['records'][1]['locator']['part_sha256'])
        self.assertEqual(projection['engine']['projector_sha256'],V1.sha(Path(N.__file__)))
        self.assertNotIn('page',projection['records'][0]['locator'])

    def test_xlsx_formula_cache_roles_empty_zero_and_external_not_followed(self):
        p=self.original('xlsx')
        with patch('socket.getaddrinfo',side_effect=AssertionError('external link must not resolve')):
            view=N.project(p,MIME['xlsx'],SPEC)
        rows={r['native']['locator']:r for r in view['records']}
        self.assertEqual(rows['原表!B1']['native']['formula'],'1+1')
        self.assertEqual(rows['原表!B1']['native']['value'],'2')
        self.assertEqual(rows['原表!B1']['native']['cache_freshness'],'not_verified')
        self.assertFalse(rows['原表!C1']['native']['cached_value_available'])
        self.assertTrue(rows['原表!D1']['native']['cached_value_available'])
        self.assertEqual(rows['原表!D1']['native']['value'],'')
        self.assertEqual(rows['原表!E1']['native']['value'],'0');self.assertIs(rows['原表!F1']['native']['value'],False)
        self.assertEqual(rows['原表!B1']['locator']['cell'],'B1')
        self.assertEqual(view['coverage']['worksheets']['原表']['state'],'hidden')
        self.assertEqual(view['coverage']['worksheet_observations']['原表']['merges'],['A2:B2'])
        self.assertTrue(any(r['status']=='external_not_followed' for r in view['coverage']['relationships']))

    def test_invalid_macro_entities_and_zip_escape_are_typed_errors(self):
        cases=[package(extra={'../escape.xml':'x'}),package(extra={'word/vbaProject.bin':b'x'}),
               package(body='<!DOCTYPE x [<!ENTITY x "unsafe">]><x>&x;</x>'),b'PK corrupt']
        for i,data in enumerate(cases):
            with self.subTest(i=i),self.assertRaisesRegex(V1.ResearchSourceError,'RESEARCH_SOURCE_NATIVE_(INVALID|UNSUPPORTED|LIMIT)'):
                N.project(self.original(payload=data),MIME['docx'],SPEC)

    def test_forged_expanded_size_duplicate_members_and_xml_depth_fail(self):
        forged=bytearray(package())
        # Forge the first entry's central uncompressed size; the actual deflate
        # stream must still be read and compared rather than trusted/truncated.
        central=forged.index(b'PK\x01\x02')
        struct.pack_into('<I',forged,central+24,1)
        deep='<a>'*140+'text'+'</a>'*140
        duplicate=io.BytesIO(package())
        with zipfile.ZipFile(duplicate,'a') as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning);z.writestr('word/document.xml','duplicate')
        for data in [bytes(forged),package(body=deep),duplicate.getvalue()]:
            with self.subTest(size=len(data)),self.assertRaisesRegex(V1.ResearchSourceError,'RESEARCH_SOURCE_NATIVE_(INVALID|LIMIT)'):
                N.project(self.original(payload=data),MIME['docx'],SPEC)

    def test_spoofed_extension_mime_legacy_OLE_and_profile_budget(self):
        for data,media,url in [(b'<html>not office</html>',MIME['docx'],'https://example/a.docx'),
                               (package('xlsx'),MIME['docx'],'https://example/a.docx'),
                               (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest','application/vnd.ms-excel','https://example/a.xls')]:
            p=self.root/'body.bin';p.write_bytes(data)
            with self.subTest(media=media),self.assertRaisesRegex(V1.ResearchSourceError,'RESEARCH_SOURCE_(FORMAT_MISMATCH|NATIVE_UNSUPPORTED)'):
                N.identify(p,media,SPEC,urls=(url,))
        with self.assertRaisesRegex(V1.ResearchSourceError,'RESEARCH_SOURCE_NATIVE_LIMIT'):
            N.project(self.original(),MIME['docx'],{**SPEC,'max_projection_chars':10})

    def test_unknown_private_policy_is_not_guessed_from_content(self):
        current=self.fixture()
        policy=current/'private/gt'/V1.POLICY_PATH
        policy.chmod(0o644);doc=V1.read(policy);doc['schema_version']='candidate-arbitrary-code';policy.write_bytes(V1.encoded(doc))
        with self.assertRaisesRegex(V1.ResearchSourceError,'RESEARCH_SOURCE_POLICY_UNSUPPORTED'):D.backend(current)

    def test_failure_has_typed_receipt_and_no_success_lock(self):
        attempt=self.fixture()
        with patch.object(V2,'fetch',side_effect=public_fetch(b'PK broken',MIME['docx'])):
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_NATIVE_INVALID'):
                RUNTIME.collect_research_sources_attempt(attempt_root=attempt)
        self.assertFalse((attempt/V1.LOCK_PATH).exists());self.assertTrue(list(attempt.glob('research-source-failure-*.json')))

    def test_rules_semantics_query_API_source_view_and_protection(self):
        attempt=self.fixture(hybrid=True,kind='xlsx')
        candidate=attempt/V1.read(attempt/'attempt-manifest.json')['paths']['candidate_original']
        before=V1.sha(candidate/'results/sources.json')
        self.collect(attempt,kind='xlsx');self.worker(attempt);RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        catalog=V1.read(attempt/'semantic/evidence-catalog.json')
        entry=next(r for r in catalog['evidence_index']['entries'] if r['reference']['path'].endswith('/body.xlsx'))
        with patch.object(N,'project',side_effect=AssertionError('query must use frozen records')):
            # Normal source verification itself reprojects, so only bypass that
            # already separately-tested check to isolate the query representation.
            with patch.object(RUNTIME,'verify_attempt',return_value={'status':'PASS'}):
                page=RUNTIME.query_evidence_attempt(attempt_root=attempt,mode='file',evidence_id=entry['id'],offset=2,limit=2)
        self.assertEqual(json.loads(page['items'][0]['text'])['locator']['cell'],'B1')
        query=V1.read(attempt/'semantic/query-log.json')['queries'][-1]
        self.assertEqual(query['coverage']['native_extraction']['content_representation'],'verified_frozen_source_records')
        sources=RUNTIME._api_evidence_sources(attempt,catalog,[])
        body=next(row for row,content,status in sources if row['path'].endswith('/body.xlsx'))
        self.assertEqual(body['content_representation'],'verified_frozen_source_records')
        binding=RUNTIME._research_source_binding(attempt,required=True)
        self.assertTrue(any(p.endswith('/text.json') for p in D.required_api_paths(attempt,binding)))
        self.assertEqual(V1.sha(candidate/'results/sources.json'),before)
        self.assertEqual(V1.read(attempt/'rule-audit.json')['research_sources']['manifest_sha256'],binding['manifest_sha256'])
        manifest=V1.read(attempt/'attempt-manifest.json'); request=V1.read(attempt/'semantic/request.json')
        runtime={'provider':'openai-responses','endpoint':'https://judge.invalid/v1/responses',
                 'endpoint_sha256':'a'*64,'credential_env':'NO_CREDENTIAL','max_output_tokens':1024,
                 'timeout_seconds':10,'max_attempts':1,'temperature':0,'reasoning_parameter':'reasoning_effort',
                 'max_input_chars':1_000_000,'max_evidence_item_chars':32}
        args=dict(manifest=manifest,request_document=request,catalog=catalog,transcript=[],
                  judge={'api_runtime':runtime},request_sha256=V1.sha(attempt/'semantic/request.json'),
                  catalog_sha256=V1.sha(attempt/'semantic/evidence-catalog.json'))
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_API_INPUT_INCOMPLETE'):
            RUNTIME._build_api_input(attempt,**args)
        runtime['max_evidence_item_chars']=200_000
        packet=RUNTIME._build_api_input(attempt,**args)
        supplied=json.loads(packet['user_prompt'])['evidence']
        self.assertTrue(any(r['content_status']=='complete' and r['path'].endswith('/text.json') for r in supplied))

    def test_complete_lifecycle_archive_rescore_and_moved_skill_zip(self):
        attempt=self.fixture();self.collect(attempt);self.finish(attempt)
        with patch.object(V2,'project',side_effect=AssertionError('archive must not extract')),patch.object(V2,'fetch',side_effect=AssertionError('archive must not fetch')):
            self.assertTrue(RUNTIME.verify_score_attempt(attempt,archived=True)['score_valid'])
        rescored=Path(RUNTIME.prepare_rescore_attempt(source_attempt_root=attempt,scoring_attempt_id='rescore',output_root=self.root/'rescore')['attempt_root'])
        self.assertEqual(V1.sha(rescored/V1.BUNDLE_PATH/'manifest.json'),V1.sha(attempt/V1.BUNDLE_PATH/'manifest.json'))
        builder=load_module('native_source_builder_test',REPO_ROOT/'tools/e2e-build/build_skill_packages.py')
        dist=self.root/'dist';built=builder.build_skill_package(REPO_ROOT,dist,'score-general-e2e',source_revision='a'*40)
        with zipfile.ZipFile(dist/built['archive']) as z:z.extractall(self.root/'installed')
        script=self.root/'installed/score-general-e2e/scripts/score_general_e2e.py'
        self.assertTrue(script.with_name('native_source_projection.py').is_file())
        moved=self.root/'moved';shutil.copytree(attempt,moved,ignore=shutil.ignore_patterns('runtime'))
        env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME'}}
        out=subprocess.run([sys.executable,'-I',str(script),'verify-score','--attempt-root',str(moved),'--archived'],cwd=self.root,env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(out.returncode,0,out.stdout+out.stderr)
        target=os.environ.get('GENERAL_E2E_NATIVE_QA_ROOT')
        if target:
            qa=Path(target);qa.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(dist/built['archive'],qa/'score-general-e2e-v0.26.0-mechanism.zip')
            (qa/'mechanism-lifecycle.json').write_bytes(V1.encoded({'synthetic_author_control_only':True,'real_Harness_or_model_experiment':False,'fixture_score_valid':True,'installed_archive_verified':True,'collector_v1_sha256':V1_SHA,'collector_v2_sha256':V1.sha(Path(V2.__file__)),'bundle':V1.read(attempt/V1.BUNDLE_PATH/'manifest.json'),'skill_build':built}))

    def test_native_reuse_is_frozen_self_contained_and_cross_profile_rejected(self):
        prior=self.fixture('prior');self.collect(prior)
        current=self.fixture('current')
        with patch.object(V2,'fetch',side_effect=AssertionError('reuse must not GET')),patch('socket.getaddrinfo',side_effect=AssertionError('reuse must not DNS')):
            result=RUNTIME.collect_research_sources_attempt(attempt_root=current,reuse_sources_from=(prior,))
        self.assertEqual((result['fresh_get_count'],result['reused_snapshot_count']),(0,1))
        capsule=next((current/V1.BUNDLE_PATH/'origins').glob('*/attempt'))
        self.assertTrue((capsule/V1.LOCK_PATH).is_file())
        old=self.fixture('old',v1=True);self.collect(old,v1=True)
        incompatible=self.fixture('cross')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_REUSE_INVALID'):
            RUNTIME.collect_research_sources_attempt(attempt_root=incompatible,reuse_sources_from=(old,))

    def test_v1_and_v2_invalid_origin_paths_preserve_admission_order_and_no_GET(self):
        evidence=[]
        for v1 in (True,False):
            label='v1' if v1 else 'v2'
            prior=self.fixture(label+'-path-prior',v1=v1);self.collect(prior,v1=v1)
            current=self.fixture(label+'-path-current',v1=v1)
            manifest=V1.read(current/'attempt-manifest.json')
            link=self.root/(label+'-linked-origin');link.symlink_to(prior,target_is_directory=True)
            unlocked=self.root/(label+'-unlocked-origin');unlocked.mkdir()
            cases=[('missing',self.root/(label+'-does-not-exist'),'RESEARCH_SOURCE_REUSE_INVALID'),
                   ('current',current,'RESEARCH_SOURCE_REUSE_INVALID'),
                   ('ancestor',current.parent,'RESEARCH_SOURCE_REUSE_INVALID'),
                   ('candidate',current/manifest['paths']['candidate_original'],'RESEARCH_SOURCE_REUSE_INVALID'),
                   ('private-GT',current/manifest['paths']['gt'],'RESEARCH_SOURCE_REUSE_INVALID'),
                   ('runtime',current/manifest['paths']['runtime_workspace'],'RESEARCH_SOURCE_REUSE_INVALID'),
                   ('symlink',link,'RESEARCH_SOURCE_REUSE_INVALID'),
                   ('missing-lock',unlocked,'RESEARCH_SOURCE_BUNDLE_REQUIRED')]
            select_backend=D.backend
            def only_current_backend(path):
                self.assertEqual(path,current,'invalid origin policy must not be opened before admission')
                return select_backend(path)
            for kind,origin,expected in cases:
                with self.subTest(policy=label,origin=kind), \
                        patch.object(D,'backend',side_effect=only_current_backend), \
                        patch.object(V1,'fetch',side_effect=AssertionError('invalid origin must not GET')) as old_get, \
                        patch.object(V2,'fetch',side_effect=AssertionError('invalid origin must not GET')) as new_get:
                    with self.assertRaises(RUNTIME.ScoringRuntimeError) as raised:
                        RUNTIME.collect_research_sources_attempt(attempt_root=current,reuse_sources_from=(origin,))
                    self.assertEqual(raised.exception.code,expected)
                    self.assertEqual(old_get.call_count+new_get.call_count,0)
                    self.assertFalse((current/V1.LOCK_PATH).exists())
                    self.assertFalse((current/V1.BUNDLE_PATH).exists())
                    evidence.append({'policy':label,'origin':kind,'error_code':raised.exception.code,
                                     'GET_count':0,'success_lock':False,'success_bundle':False,
                                     'origin_backend_or_manifest_opened':False})
        target=os.environ.get('GENERAL_E2E_NATIVE_QA_ROOT')
        if target:
            qa=Path(target);qa.mkdir(parents=True,exist_ok=True)
            (qa/'invalid-origin-path-controls.json').write_bytes(V1.encoded({
                'author_control_only_not_Harness':True,'cases':evidence,'case_count':len(evidence)}))

    def test_original_policy_stage_and_input_errors_precede_invalid_origin(self):
        missing=self.root/'no-such-origin'
        disabled=Fixture(self.root/'disabled-source').prepare('disabled')
        with self.assertRaises(RUNTIME.ScoringRuntimeError) as raised:
            RUNTIME.collect_research_sources_attempt(attempt_root=disabled,reuse_sources_from=(missing,))
        self.assertEqual(raised.exception.code,'RESEARCH_SOURCE_POLICY_REQUIRED')
        for old in (True,False):
            label='v1' if old else 'v2'
            complete=self.fixture(label+'-already-collected',v1=old);self.collect(complete,v1=old)
            late=self.fixture(label+'-too-late',v1=old);(late/'worker').mkdir()
            budget=self.fixture(label+'-input-error',v1=old)
            module=V1 if old else V2
            with self.subTest(policy=label),patch.object(module,'fetch',side_effect=AssertionError('must not GET')):
                for attempt,code in [(complete,'RESEARCH_SOURCE_COLLECTION_EXISTS'),(late,'RESEARCH_SOURCE_COLLECTION_TOO_LATE')]:
                    with self.assertRaises(RUNTIME.ScoringRuntimeError) as raised:
                        RUNTIME.collect_research_sources_attempt(attempt_root=attempt,reuse_sources_from=(missing,))
                    self.assertEqual(raised.exception.code,code)
                with patch.object(module,'_candidate_inputs',side_effect=V1.ResearchSourceError('RESEARCH_SOURCE_BUDGET_INSUFFICIENT','fixture source limit')):
                    with self.assertRaises(RUNTIME.ScoringRuntimeError) as raised:
                        RUNTIME.collect_research_sources_attempt(attempt_root=budget,reuse_sources_from=(missing,))
                    self.assertEqual(raised.exception.code,'RESEARCH_SOURCE_BUDGET_INSUFFICIENT')
                for attempt in (late,budget):self.assertFalse((attempt/V1.LOCK_PATH).exists())

    def test_native_raw_unprojected_part_cannot_cover_reuse_quote(self):
        prior=self.fixture('hidden-prior')
        payload=package(extra={'word/unreferenced.xml':'<x>raw-only-token</x>'})
        with patch.object(V2,'fetch',side_effect=public_fetch(payload,MIME['docx'])):
            RUNTIME.collect_research_sources_attempt(attempt_root=prior)
        current=self.fixture('hidden-current',quote='raw-only-token')
        with patch.object(V2,'fetch',side_effect=public_fetch(payload,MIME['docx'])) as getter:
            result=RUNTIME.collect_research_sources_attempt(attempt_root=current,reuse_sources_from=(prior,))
        self.assertEqual(getter.call_count,1)
        self.assertEqual((result['fresh_get_count'],result['reused_snapshot_count']),(1,0))

    def test_ordinary_candidate_native_query_keeps_legacy_helper(self):
        fixture=Fixture(self.root/'ordinary',grading_type='llm_judge',
                        grading_weights={'automated':0.,'llm_judge':1.},llm_judge_rubric=RUBRIC)
        (fixture.candidate/'original.docx').write_bytes(package())
        entries,digest=RUNTIME._inventory_tree(fixture.candidate)
        ap=fixture.candidate.parent/'candidate-artifact.json';artifact=V1.read(ap);artifact.update(entries=entries,expected_sha256=digest);ap.write_bytes(V1.encoded(artifact))
        execution=V1.read(fixture.execution_record);execution['candidate']['frozen_sha256']=digest;fixture.execution_record.write_bytes(V1.encoded(execution))
        attempt=fixture.prepare('ordinary-native')
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        catalog=V1.read(attempt/'semantic/evidence-catalog.json')
        entry=next(r for r in catalog['evidence_index']['entries'] if r['reference']['path'].endswith('/original.docx'))
        result=RUNTIME.query_evidence_attempt(attempt_root=attempt,mode='file',evidence_id=entry['id'],offset=1,limit=1)
        self.assertEqual(json.loads(result['items'][0]['text'])['locator'],'table:1/row:1/cell:1')
        log=V1.read(attempt/'semantic/query-log.json')['queries'][-1]
        self.assertEqual(log['coverage']['native_extraction']['engine']['version'],'wildclawbench.docx-text/v1')

    def test_normal_projection_drift_and_archive_byte_tamper_fail(self):
        attempt=self.fixture();self.collect(attempt)
        with patch.object(V2,'project',return_value={}):
            with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_PROJECTION_DRIFT'):RUNTIME.verify_attempt(attempt)
        body=next((attempt/V1.BUNDLE_PATH).rglob('body.docx'));body.chmod(0o644);body.write_bytes(b'changed')
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError,'RESEARCH_SOURCE_BUNDLE_DRIFT'):RUNTIME.verify_attempt(attempt,require_runtime=False)

    def test_v1_rule_finalize_archive_and_reuse_regression_without_network(self):
        old=self.fixture('old-complete',v1=True);self.collect(old,v1=True);self.finish(old)
        with patch.object(V1,'project',side_effect=AssertionError('v1 archive uses frozen extraction')):
            self.assertTrue(RUNTIME.verify_score_attempt(old,archived=True)['score_valid'])
        current=self.fixture('old-reuse',v1=True)
        with patch.object(V1,'fetch',side_effect=AssertionError('v1 reuse no GET')):
            result=RUNTIME.collect_research_sources_attempt(attempt_root=current,reuse_sources_from=(old,))
        self.assertEqual(result['reused_snapshot_count'],1)
        self.assertEqual(V1.read(current/V1.BUNDLE_PATH/'manifest.json')['collector_sha256'],V1_SHA)


if __name__ == '__main__':
    unittest.main()
