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
    trials = [benchmark.trial(editor, output / f'trace-{index}.json', observe_dom=True) for index in range(1, 4)]
    observer_trials = [benchmark.trial(editor, observe_dom=True) for _ in range(3)]
    ablated_trials = ([benchmark.trial(editor, output / f'ablated-trace-{index}.json',
                                      observe_dom=True, ablate_frames=True)
                       for index in range(1, 4)] if args.variant == 'candidate' else [])
    ablated_observer_trials = ([benchmark.trial(editor, observe_dom=True, ablate_frames=True)
                                for _ in range(3)] if args.variant == 'candidate' else [])
    all_trials = [*trials, *observer_trials, *ablated_trials, *ablated_observer_trials]
    for item in all_trials:
        if item['valid']:
            observations = item['domObservations']
            if observations['dropped'] or not any(entry['exact'] for entry in observations['entries']):
                item.update(valid=False, error='DOM observation missing exact readiness or dropped entries')
    for index, item in enumerate(trials, 1):
        if not item['valid']:
            continue
        events = json.loads((output / f'trace-{index}.json').read_text())['traceEvents']
        markers = [event for event in events if event.get('name', '').startswith('file-open-rpc:')]
        item['rpcMarkerCount'] = len(markers)
        if not markers:
            item.update(valid=False, error='trace contains no RPC markers')
    for index, item in enumerate(ablated_trials, 1):
        if not item['valid']:
            continue
        events = json.loads((output / f'ablated-trace-{index}.json').read_text())['traceEvents']
        item['immediateFrameCount'] = sum(event.get('name') == 'file-open-ablation:immediate-frame'
                                          for event in events)
        if not item['immediateFrameCount']:
            item.update(valid=False, error='frame ablation did not execute')
    (output / 'diagnostic.json').write_text(json.dumps({
        'diagnosticOnly': True, 'editor': editor,
        'host': {'machine': platform.machine(), 'kernel': platform.release(),
                 'logicalCpuCount': os.cpu_count(),
                 'runUrl': os.environ.get('BENCHMARK_RUN_URL'),
                 'commit': os.environ.get('BENCHMARK_COMMIT')},
        'note': 'Tracing perturbs timing. These trials are excluded from the protocol-v1 report. '
                'CDP durations include concurrent application work; do not subtract them to infer app time.',
        'trials': trials, 'observerOnlyTrials': observer_trials,
        'frameAblationTrials': ablated_trials,
        'frameAblationObserverOnlyTrials': ablated_observer_trials,
    }, indent=2) + '\n')
    if not all(item['valid'] for item in all_trials):
        raise SystemExit('diagnostic capture failed; inspect diagnostic.json')


if __name__ == '__main__':
    main()
