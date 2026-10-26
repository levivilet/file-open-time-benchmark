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
    parser.add_argument('--variant', choices=['baseline', 'candidate', 'candidate-coalesced'], required=True)
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
    trials = [benchmark.trial(editor, output / f'trace-{index}.json',
                              skip_first_pending=args.variant == 'candidate-coalesced') for index in range(1, 4)]
    for index, item in enumerate(trials, 1):
        if not item['valid']:
            continue
        events = json.loads((output / f'trace-{index}.json').read_text())['traceEvents']
        markers = [event for event in events if event.get('name', '').startswith('file-open-rpc:')]
        item['rpcMarkerCount'] = len(markers)
        if args.variant == 'candidate-coalesced' and not any(
                event.get('name') == 'file-open-ablation:skip-first-render' for event in events):
            item.update(valid=False, error='ablation did not skip the first render')
        if not markers:
            item.update(valid=False, error='trace contains no RPC markers')
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
