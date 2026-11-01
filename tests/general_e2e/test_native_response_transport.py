from copy import deepcopy
import unittest

from tests.general_e2e.test_local_scoring_runtime import RUNTIME

TRANSPORT=RUNTIME.native_response_transport


class NativeResponseTransportTests(unittest.TestCase):
    def test_only_identical_review_query_ids_are_deduplicated_in_declared_locations(self):
        manifest={'runtime':{'native_response_transport_profile':TRANSPORT.PROFILE}}
        response={'criteria':[{'key':'c','score':.5,'reason':'保持原判定','evidence_ids':['e1'],
            'review':{'query_ids':['q1','q2','q1']}}],
            'run_validity':{'status':'valid','review':{'query_ids':['q2','q2']}},
            'capability_evidence_statuses':{'ability':{'score':.75,'review':{'query_ids':['q1','q1']}}}}
        original=deepcopy(response)
        normalized,proof=TRANSPORT.normalize(manifest,response,'a'*64)
        self.assertEqual(response,original)
        self.assertEqual(normalized['criteria'][0]['review']['query_ids'],['q1','q2'])
        self.assertEqual(normalized['criteria'][0]['score'],.5)
        self.assertEqual(normalized['criteria'][0]['evidence_ids'],['e1'])
        self.assertEqual(proof['removed_query_reference_count'],3)
        self.assertEqual(TRANSPORT.normalize({},response,'a'*64),(response,None))

    def test_unknown_or_malformed_ids_are_not_invented_or_repaired(self):
        manifest={'runtime':{'native_response_transport_profile':TRANSPORT.PROFILE}}
        response={'criteria':[{'review':{'query_ids':['unknown','unknown']}},
                              {'review':{'query_ids':['q1',None,'q1']}}]}
        normalized,_=TRANSPORT.normalize(manifest,response,'a'*64)
        self.assertEqual(normalized['criteria'][0]['review']['query_ids'],['unknown'])
        self.assertEqual(normalized['criteria'][1]['review']['query_ids'],['q1',None,'q1'])


if __name__=='__main__':unittest.main()
