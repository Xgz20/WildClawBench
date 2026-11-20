import json
import unittest
from project.stream import SSEDecoder
from project import state,render

def event(n,kind='body',text='hello'):
    value={'request_id':'public','seq':n,'kind':kind}
    if kind=='body':value['text']=text
    return {'id':'e'+str(n),'event':'message','data':json.dumps(value)}
class PublicCompatibility(unittest.TestCase):
    def test_whole_frame_decode(self):
        self.assertEqual(SSEDecoder().feed(b'id: e1\ndata: {}\n\n'),[{'id':'e1','event':'message','data':'{}'}])
    def test_normal_body(self):
        s=state.apply_event(state.new_state('public'),event(1));self.assertEqual(state.snapshot(s)['body'],'hello')
    def test_explicit_done(self):
        s=state.apply_event(state.new_state('public'),event(1,'done'));self.assertTrue(state.snapshot(s)['done'])
    def test_streaming_render_is_not_completed(self):
        s=state.apply_event(state.new_state('public'),event(1));self.assertFalse(render.render_state(s)['completed'])
