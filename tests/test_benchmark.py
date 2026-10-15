import copy
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import benchmark
import report


def trial(repeat, seconds=0.2):
    return {'valid': True, 'repeat': repeat, 'seconds': seconds,
            'documentIdentity': 'hello.txt, Tab', 'visibleContent': 'hello world'}


def result(editor, durations=(0.2, 0.3, 0.1)):
    return {'editor': editor, 'protocol': benchmark.PROTOCOL,
            'host': {'machine': 'aarch64'},
            'trials': [trial(index, value) for index, value in enumerate(durations, 1)]}


class BenchmarkTest(unittest.TestCase):
    def test_protocol_has_real_click_boundary_and_visible_completion(self):
        self.assertIn('mouse click', benchmark.PROTOCOL['action'])
        self.assertIn('mousePressed', benchmark.PROTOCOL['boundary'])
        self.assertIn('visible editor text', benchmark.PROTOCOL['completion'])
        self.assertEqual(benchmark.PROTOCOL['repeats'], 3)
        self.assertIn('U+00A0', benchmark.PROTOCOL['contentNormalization'])

    def test_fixture_completion_requires_identity_and_exact_visible_content(self):
        fixture = Path('/tmp/workspace/hello.txt')
        self.assertTrue(benchmark.fixture_matches('vscode',
                                                   {'identity': 'hello.txt, Tab', 'content': 'hello world'}, fixture))
        self.assertTrue(benchmark.fixture_matches('vscode',
                                                   {'identity': 'hello.txt, Tab', 'content': 'hello\u00a0world'}, fixture))
        self.assertTrue(benchmark.fixture_matches('lvce',
                                                   {'identity': '/tmp/workspace/hello.txt', 'content': 'hello world'}, fixture))
        self.assertFalse(benchmark.fixture_matches('lvce',
                                                    {'identity': '/tmp/other/hello.txt', 'content': 'hello world'}, fixture))
        self.assertFalse(benchmark.fixture_matches('vscode',
                                                    {'identity': 'hello.txt', 'content': 'hello world!'}, fixture))
        self.assertFalse(benchmark.fixture_matches('vscode',
                                                    {'identity': 'hello.txt', 'content': 'hello world\n'}, fixture))
        self.assertFalse(benchmark.fixture_matches('vscode',
                                                    {'identity': 'hello.txt', 'content': 'hello  world'}, fixture))

    def test_report_rejects_failed_open_and_bad_duration_or_evidence(self):
        editor = report.EDITORS[0]
        report.validate_result(result(editor), editor['id'])
        invalid = [{'valid': False}, {'seconds': 0}, {'seconds': float('nan')},
                   {'seconds': True}, {'seconds': 16}, {'seconds': 15},
                   {'documentIdentity': 'other.txt'}, {'visibleContent': 'wrong'},
                   {'visibleContent': 'hello world\n'},
                   {'visibleContent': None}, {'repeat': 4}, {'repeat': True}]
        for changes in invalid:
            broken = copy.deepcopy(result(editor))
            broken['trials'][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                report.validate_result(broken, editor['id'])
        self.assertTrue(math.isfinite(0.1))

    def test_report_requires_both_editors_matching_protocol_and_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, 'missing'):
                report.load_results(root)
            for editor in report.EDITORS:
                folder = root / f"open-{editor['id']}"
                folder.mkdir()
                (folder / 'results.json').write_text(json.dumps(result(editor)))
            self.assertEqual(len(report.load_results(root)), 2)
            data_path = root / f"open-{report.EDITORS[0]['id']}" / 'results.json'
            broken = result(report.EDITORS[0])
            broken['protocol'] = {'version': 2}
            data_path.write_text(json.dumps(broken))
            with self.assertRaisesRegex(ValueError, 'protocol'):
                report.load_results(root)
            data_path.write_text(json.dumps(result(dict(report.EDITORS[0], version='wrong'))))
            with self.assertRaisesRegex(ValueError, 'version'):
                report.load_results(root)

    def test_report_chart_and_raw_json_match_trial_data(self):
        items = [{'editor': editor, 'data': result(editor, durations)} for editor, durations in
                 zip(report.EDITORS, [(0.2, 0.3, 0.1), (0.4, 0.5, 0.3)])]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report.build_report(items, output, 'https://example.test/run', 'abc123')
            payload = json.loads((output / 'report.json').read_text())
            self.assertEqual([entry['medianSeconds'] for entry in payload['editors']], [0.2, 0.4])
            first = payload['editors'][0]
            raw = json.loads((output / first['raw']).read_text())
            self.assertEqual([trial['seconds'] for trial in raw['trials']], [0.2, 0.3, 0.1])
            page = (output / 'index.html').read_text()
            self.assertIn('Median open time', page)
            self.assertIn('elapsed seconds', page)
            self.assertIn('Raw JSON', page)


if __name__ == '__main__':
    unittest.main()
