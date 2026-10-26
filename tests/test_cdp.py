import base64
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from cdp import Page


class Socket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    def send(self, data):
        self.sent.append(json.loads(data))

    def recv(self):
        return json.dumps(next(self.messages))


class TraceTest(unittest.TestCase):
    def page(self, messages):
        page = Page.__new__(Page)
        page.counter = 0
        page.events = []
        page.timings = []
        page.socket = Socket(messages)
        return page

    def test_trace_completion_before_command_response_and_mixed_stream_chunks(self):
        page = self.page([
            {'method': 'Tracing.tracingComplete', 'params': {'stream': 'trace'}},
            {'id': 1, 'result': {}},
            {'id': 2, 'result': {'data': '{"traceEvents":', 'eof': False}},
            {'id': 3, 'result': {'data': base64.b64encode(b'[]}').decode(),
                                 'base64Encoded': True, 'eof': True}},
            {'id': 4, 'result': {}},
        ])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'trace.json'
            page.stop_trace(output)
            self.assertEqual(json.loads(output.read_text()), {'traceEvents': []})
        self.assertEqual(page.socket.sent[-1]['method'], 'IO.close')
        self.assertEqual(len(page.timings), 4)

    def test_trace_data_loss_is_a_failed_capture(self):
        page = self.page([
            {'id': 1, 'result': {}},
            {'method': 'Tracing.tracingComplete', 'params': {'stream': 'trace', 'dataLossOccurred': True}},
            {'id': 2, 'result': {'data': '{}', 'eof': True}},
            {'id': 3, 'result': {}},
        ])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'lost events'):
                page.stop_trace(Path(directory) / 'trace.json')
        self.assertEqual(page.socket.sent[-1]['method'], 'IO.close')
