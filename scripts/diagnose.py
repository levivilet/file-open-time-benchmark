"""Capture diagnostic-only opens; never feed instrumented timings into the report."""
import argparse
import json
import os
import platform
from pathlib import Path

import benchmark
import install

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=['baseline', 'candidate'], required=True)
    args = parser.parse_args()
    lock = 'baseline.lock.json' if args.variant == 'baseline' else 'editors.lock.json'
    editor = next(item for item in json.loads((ROOT / 'config' / lock).read_text())
                  if item['id'] == 'lvce')
    apps = ROOT / '.tmp/apps'
    apps.mkdir(parents=True, exist_ok=True)
    archive = apps / editor['archive']
    install.download(editor, archive)
    install.extract(editor, archive, apps / 'lvce')
    output = ROOT / 'results' / 'diagnostic' / args.variant
    output.mkdir(parents=True, exist_ok=True)
    trials = [benchmark.trial(editor, output / f'trace-{index}.json') for index in range(1, 4)]
    (output / 'diagnostic.json').write_text(json.dumps({
        'diagnosticOnly': True, 'editor': editor,
        'host': {'machine': platform.machine(), 'kernel': platform.release(),
                 'logicalCpuCount': os.cpu_count(),
                 'runUrl': os.environ.get('BENCHMARK_RUN_URL'),
                 'commit': os.environ.get('BENCHMARK_COMMIT')},
        'note': 'Tracing perturbs timing. These trials are excluded from the protocol-v1 report. '
                'CDP durations include concurrent application work; do not subtract them to infer app time.',
        'trials': trials,
    }, indent=2) + '\n')
    if not all(item['valid'] for item in trials):
        raise SystemExit('diagnostic capture failed; inspect diagnostic.json')


if __name__ == '__main__':
    main()
