import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from src.utils import judge_shim
from src.cli_scoring import score


class CliScoringTests(unittest.TestCase):
    def test_judge_channel_roundtrips_original_messages_and_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def responder():
                for _ in range(50):
                    requests = list(root.glob('*.request.json'))
                    if requests:
                        path = requests[0]
                        data = json.loads(path.read_text())
                        self.assertEqual(data['messages'], [{'role': 'user', 'content': '原 Rubric'}])
                        path.with_name(path.name.replace('.request.', '.response.')).write_text(json.dumps({'text': '{"scores":{"C1":0}}', 'model': 'judge'}))
                        return
                    time.sleep(.02)
                raise AssertionError('request missing')
            thread = threading.Thread(target=responder)
            thread.start()
            with patch.dict('os.environ', {'WCB_JUDGE_CHANNEL': str(root)}):
                response = judge_shim.OpenAI().chat.completions.create(model='judge', messages=[{'role': 'user', 'content': '原 Rubric'}])
            thread.join()
            self.assertEqual(json.loads(response.choices[0].message.content)['scores']['C1'], 0)
            self.assertIsNone(response.usage)

    def test_scoring_rejects_modified_frozen_input_before_docker(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'manifest.json').write_text(json.dumps({'files': [], 'image': 'frozen'}))
            (root / 'task.json').write_text('{}')
            with patch('src.cli_scoring.docker') as docker:
                with self.assertRaisesRegex(RuntimeError, 'INPUT_DRIFT'):
                    score(root, root / 'result', {'transport': 'api'})
                docker.assert_not_called()
