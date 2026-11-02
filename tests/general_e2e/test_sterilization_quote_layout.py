from copy import deepcopy
from io import BytesIO
from pathlib import Path
import ast
import hashlib
import json
import math
import re
import tempfile
import unicodedata
import unittest
import openpyxl

from tests.general_e2e.test_local_scoring_runtime import RUNTIME,REPO_ROOT
from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source

QUOTE=RUNTIME.sterilization_quote_layout


class SterilizationQuoteLayoutTests(unittest.TestCase):
    def source(self):
        file=next((REPO_ROOT/'tasks/general_e2e').rglob(QUOTE.TASK+'.md'));_,sections,_=_parse_task_source(file)
        return _strip_codeblock(sections['Automated Checks'])

    def fixed(self):
        source=self.source();contract={'task_id':QUOTE.TASK,'automated_checks':source}
        marker=QUOTE.marker(contract,QUOTE.CONTRACT_SHA,QUOTE.DATASET);self.assertIsNotNone(marker)
        manifest={'identity':{'task_id':QUOTE.TASK},'digests':{'contract_sha256':QUOTE.CONTRACT_SHA},
            'dataset':QUOTE.DATASET,'runtime':{'sterilization_quote_layout_profile':marker}}
        fixed,receipt=RUNTIME._effective_rule_source(manifest,source)
        return source,fixed,receipt,manifest

    def helpers(self,source):
        parsed=ast.parse(source);nodes=[n for n in parsed.body if isinstance(n,ast.FunctionDef) and n.name in {'norm','text','numeric','duration','role'}]
        patterns=next(ast.literal_eval(n.value) for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PATTERNS' for t in n.targets))
        namespace={'re':re,'math':math,'unicodedata':unicodedata,'PATTERNS':patterns}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'<trusted-field-transport-functions>','exec'),namespace)
        return namespace

    def test_exact_profile_changes_only_role_fallback_and_all_other_original_code_is_identical(self):
        source,fixed,receipt,manifest=self.fixed()
        old='    return next((k for k,rx in PATTERNS.items() if re.fullmatch(rx,s)),None)'
        aliases={QUOTE.normalized(k):v for k,v in QUOTE.HEADINGS.items()}
        self.assertEqual(fixed,source.replace(old,old+' or '+repr(aliases)+'.get(s)'))
        before=ast.parse(source);after=ast.parse(fixed)
        self.assertEqual([ast.dump(n) for n in before.body if not isinstance(n,ast.FunctionDef) or n.name!='role'],
            [ast.dump(n) for n in after.body if not isinstance(n,ast.FunctionDef) or n.name!='role'])
        self.assertFalse(receipt['candidate_rewritten']);self.assertFalse(receipt['numeric_decisions_assigned'])
        self.assertEqual(RUNTIME._effective_rule_source({},source),(source,None))
        bad=deepcopy(manifest);bad['dataset']['digest']='0'*64
        with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(bad,source)

    def test_three_explicit_headings_and_original_time_ranges_without_broadening_ambiguous_labels(self):
        source,fixed,_,_=self.fixed();old=self.helpers(source);new=self.helpers(fixed)
        for heading,role in QUOTE.HEADINGS.items():
            self.assertIsNone(old['role'](heading));self.assertEqual(new['role'](heading),role)
        for heading in ['Total','Delivery','Validity','Estimated Delivery (from request)','Est. Total incl. goods (EUR)','Rate Validity USD']:
            self.assertEqual(new['role'](heading),old['role'](heading))
        for text,expected in [('24-26 days (3 weeks production + 3-5 days transit)',(24.,26.)),('14 days from issue',(14.,14.))]:
            self.assertEqual(new['duration'](text),expected);self.assertEqual(old['duration'](text),expected)

    def test_blocker_binds_identity_actual_headers_and_original_formulas_without_assigning_scores(self):
        source=self.source();contract={'task_id':QUOTE.TASK,'automated_checks':source}
        identity={'task_id':QUOTE.TASK,'scoring_attempt_id':'synthetic-score','execution_attempt_id':'synthetic-exec','batch_id':'synthetic-batch','unit_id':'synthetic-unit'}
        judge={'protocol':'codex-agent-judge-v1','model':'synthetic-judge','reasoning_effort':'high'}
        workbook=openpyxl.Workbook();sheet=workbook.active;sheet.title='Blad1'
        for cell,heading in [('F23','Est. Total incl. goods (USD)'),('C23','Estimated Delivery (from order)'),('E23','Rate Validity')]:sheet[cell]=heading
        sheet['F24']='=$F$11+B24';stream=BytesIO();workbook.save(stream);raw=stream.getvalue();workbook.close()
        conflicts=[{'header':h,'candidate_sheet':'Blad1','header_cell':c,'rule_extracted':{'synthetic.original':None},'formulas':{'F24':'=$F$11+B24'} if c=='F23' else {}}
            for c,h in [('F23','Est. Total incl. goods (USD)'),('C23','Estimated Delivery (from order)'),('E23','Rate Validity')]]
        blocker={'schema_version':'general-e2e-independent-judge-blocker/v1','identity':identity,'judge':judge,
            'error_code':'FROZEN_RULE_REASONABLE_LAYOUT_EXTRACTION_MISMATCH','total_score':None,'formal_score_completed':False,
            'evidence_review':{'all_six_declared_evidence_files_read_completely':True,'candidate_sha256':hashlib.sha256(raw).hexdigest()},'conflicts':conflicts,
            'actions':dict.fromkeys(['rules_rerun','candidate_modified','rule_component_modified','semantic_response_imported','finalize_run','verify_score_passed'],False)}
        manifest={'identity':identity,'judge':judge,'dataset':QUOTE.DATASET,'digests':{'contract_sha256':QUOTE.CONTRACT_SHA},'paths':{'candidate_original':'candidate'}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'candidate').mkdir();(root/'candidate/quote.xlsx').write_bytes(raw)
            self.assertTrue(QUOTE.validate_blocker(root,manifest,contract,blocker))
            bad=deepcopy(blocker);bad['conflicts'][0]['formulas']['F24']='=999'
            with self.assertRaisesRegex(ValueError,'FORMULA_DRIFT'):QUOTE.validate_blocker(root,manifest,contract,bad)
            bad=deepcopy(blocker);bad['identity']['execution_attempt_id']='other'
            with self.assertRaisesRegex(ValueError,'BLOCKER_INVALID'):QUOTE.validate_blocker(root,manifest,contract,bad)


if __name__=='__main__':unittest.main()
