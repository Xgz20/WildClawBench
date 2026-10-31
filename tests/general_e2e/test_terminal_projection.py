import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from eval_general_e2e.contracts import astronstudio_terminal_projection as T

ROOT = Path(__file__).resolve().parents[2]
path = ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/trace_handoff.py'
spec = importlib.util.spec_from_file_location('terminal_handoff_test', path)
HANDOFF = importlib.util.module_from_spec(spec);spec.loader.exec_module(HANDOFF)
encoded = lambda value: (json.dumps(value, ensure_ascii=False)+'\n').encode()
lines = lambda rows: b''.join(encoded(row) for row in rows)


def fixture():
    identity = dict(batch_id='b', unit_id='u', task_id='t', attempt_id='a')
    session = dict(thread_id='thread', turn_id='turn', session_id='session', cwd='/synthetic/workspace')
    state = dict(identity=identity, phase='COMPLETED', session={**session, 'verified': True, 'native_status': 'running'},
                 execution=dict(business_status='completed', error=None, finished_at='2026-10-31T00:00:01Z'),
                 prompt=dict(send_status='sent', sha256=T.sha('question\u2028text'.encode())),
                 send=dict(dispatch_attempt_count=1), evidence=dict(final_response_sha256=T.sha(b'final\n')),
                 history=[dict(phase='RUNNING', event='TERMINAL_FINAL_RESPONSE_BOUND',
                               source='completed-turn.assistant_message_id', message_id='message'),
                          dict(phase='COMPLETED', event='NATIVE_TERMINAL_OBSERVED', native_status='running',
                               turn_state='completed', at='2026-10-31T00:00:01Z')])
    def row(kind, **payload):return dict(type=kind, timestamp='2026-10-31T00:00:00Z', payload=payload)
    sdk = [row('session_meta', id='session', cwd=session['cwd']),
           row('event_msg', type='task_started', turn_id='turn'),
           row('turn_context', turn_id='turn', cwd=session['cwd']),
           row('event_msg', type='user_message', message='question\u2028text'),
           row('response_item', type='message', role='assistant', content=[dict(type='output_text', text='final')]),
           row('event_msg', type='task_complete', turn_id='turn', last_agent_message='final')]
    def event(n, kind, content, line, **extra):
        return dict(identity=identity, sequence=n, type=kind, content=content,
                    source=dict(raw_ref=T.SDK_PATH+'#L'+str(line)), **extra)
    events = [event(0, 'user_message', 'question\u2028text', 4),
              event(1, 'assistant_message', 'final', 5, final=True),
              event(2, 'status', 'turn.completed', 6, status=dict(turn_id='turn'))]
    index = dict(identity=identity, session=session,
                 canonical_source_policy=dict(id='bound-native-sdk-canonical/v1'),
                 completeness=dict(status='complete', omitted_event_count=0, missing=[]))
    return state, index, sdk, events


def input_bytes(state, index, sdk, events):
    sdk_bytes, transcript = lines(sdk), lines(events)
    index = copy.deepcopy(index)
    index['raw_trace'] = [dict(path=T.SDK_PATH, sha256=T.sha(sdk_bytes), size=len(sdk_bytes))]
    index['transcript'] = dict(path='transcript.jsonl', sha256=T.sha(transcript), size=len(transcript), event_count=len(events))
    return encoded(state), index, sdk_bytes, transcript


def write_trace(root, inputs):
    state_bytes, index, sdk, transcript = inputs
    proof = T.derive(*inputs)
    blobs = {T.STATE_PATH: state_bytes, T.PROOF_PATH: encoded(proof), T.SDK_PATH: sdk, 'transcript.jsonl': transcript}
    index['binding_evidence'] = [dict(path=k, sha256=T.sha(blobs[k]), size=len(blobs[k])) for k in (T.STATE_PATH, T.PROOF_PATH)]
    for name, data in blobs.items():
        p=root/name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(data)
    (root/'trace-index.json').write_bytes(encoded(index))
    return index, proof


class TerminalProjectionTests(unittest.TestCase):
    def test_exact_native_completion_preserves_original_projection_and_physical_lines(self):
        inputs=input_bytes(*fixture());proof=T.derive(*inputs)
        self.assertEqual(proof['sdk']['terminal_line'], 6)
        self.assertEqual(proof['original_projection_status'], 'running')
        self.assertEqual(proof['original_state_sha256'], T.sha(inputs[0]))
        self.assertFalse(proof['prompts_resent']);self.assertFalse(proof['scoring_rules_changed'])
        self.assertNotIn('final', proof['sdk'])

    def test_wrong_cancelled_missing_duplicate_or_changed_native_evidence_is_rejected(self):
        mutations = [lambda s,i,r,e:r.pop(),
                     lambda s,i,r,e:r.append(copy.deepcopy(r[-1])),
                     lambda s,i,r,e:r[-1]['payload'].update(type='turn_aborted'),
                     lambda s,i,r,e:r[-1]['payload'].update(turn_id='other'),
                     lambda s,i,r,e:r[0]['payload'].update(id='other'),
                     lambda s,i,r,e:r[2]['payload'].update(cwd='/other'),
                     lambda s,i,r,e:r[3]['payload'].update(message='different'),
                     lambda s,i,r,e:r[-1]['payload'].update(last_agent_message='different'),
                     lambda s,i,r,e:r.append(copy.deepcopy(r[4])),
                     lambda s,i,r,e:r.append(dict(type='event_msg',payload=dict(type='task_started',turn_id='other'))),
                     lambda s,i,r,e:r.append(dict(type='turn_context',payload=dict(turn_id='other',cwd=s['session']['cwd']))),
                     lambda s,i,r,e:r.append(dict(type='event_msg',payload=dict(type='agent_reasoning',text='late'))),
                     lambda s,i,r,e:r.append(dict(type='event_msg',payload=dict(type='error',message='late'))),
                     lambda s,i,r,e:r.append(dict(type='world_state',payload=dict(state={}))),
                     lambda s,i,r,e:r.append(dict(type='response_item',payload=dict(type='message',role='user',content=[]))),
                     lambda s,i,r,e:r.insert(4,copy.deepcopy(r[3])),
                     lambda s,i,r,e:r.pop(2),
                     lambda s,i,r,e:s['history'][-1].update(turn_state='failed'),
                     lambda s,i,r,e:s['history'][0].update(source='unbound'),
                     lambda s,i,r,e:s['send'].update(dispatch_attempt_count=2),
                     lambda s,i,r,e:s['session'].update(native_status='needs_attention'),
                     lambda s,i,r,e:e[-1]['source'].update(raw_ref=T.SDK_PATH+'#L5'),
                     lambda s,i,r,e:i['canonical_source_policy'].update(id='provider-reconciled'),
                     lambda s,i,r,e:i['completeness'].update(status='partial')]
        for n, mutate in enumerate(mutations):
            with self.subTest(case=n):
                values=fixture();mutate(*values)
                with self.assertRaises(ValueError):T.derive(*input_bytes(*values))

    def test_proof_forgery_is_rejected_after_its_declared_hash_is_updated(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inputs=input_bytes(*fixture());index,proof=write_trace(root,inputs)
            self.assertEqual(T.verify_index(root,index),proof)
            proof['sdk']['terminal_line']=5;raw=encoded(proof);(root/T.PROOF_PATH).write_bytes(raw)
            ref=next(r for r in index['binding_evidence'] if r['path']==T.PROOF_PATH)
            ref.update(sha256=T.sha(raw),size=len(raw))
            with self.assertRaisesRegex(ValueError,'PROOF_CONTENT'):T.verify_index(root,index)

    def test_running_projection_without_both_original_and_proof_stays_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inputs=input_bytes(*fixture());index,proof=write_trace(root,inputs)
            index['binding_evidence'].pop()
            with self.assertRaisesRegex(ValueError,'PROOF_SCOPE'):T.verify_index(root,index)
            index['binding_evidence']=[]
            with self.assertRaisesRegex(ValueError,'PROOF_REQUIRED'):T.verify_index(root,index,state_bytes=inputs[0])

    def test_scoring_handoff_recomputes_proof_and_preserves_it_when_archived(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);unit=root/'unit';trace=unit/'trace';trace.mkdir(parents=True)
            inputs=input_bytes(*fixture());index,proof=write_trace(trace,inputs)
            state=json.loads(inputs[0]);execution={k:state[k] for k in ('identity','phase','execution','prompt','session')}
            execution['evidence']=dict(trace_index_path='trace/trace-index.json',transcript_path='trace/transcript.jsonl')
            attempt=root/'attempt';attempt.mkdir()
            ref=HANDOFF.freeze(unit,execution,attempt,required=True)
            self.assertEqual(ref['terminal_projection_profile']['id'],T.PROFILE)
            HANDOFF.verify(attempt,ref,execution)
            archived=root/'archived';HANDOFF.copy_frozen(attempt,archived,ref,execution)
            self.assertEqual((archived/'trace'/T.STATE_PATH).read_bytes(),inputs[0])
            bad=dict(ref);bad.pop('terminal_projection_profile')
            with self.assertRaisesRegex(ValueError,'REFERENCE_MISMATCH'):HANDOFF.verify(archived,bad,execution)

    def test_unaffected_trace_has_no_new_profile(self):
        state,index,_,_=fixture();state['session']['native_status']='completed'
        self.assertIsNone(T.verify_index(Path('/unused'),index,state_bytes=encoded(state)))
