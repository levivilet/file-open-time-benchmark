"""Run the pinned LVCE control using the unchanged untraced timing protocol."""
import json
import os
import platform
from pathlib import Path

import benchmark
import install

ROOT = Path(__file__).resolve().parent.parent


def main():
    editor = json.loads((ROOT / 'config/baseline.lock.json').read_text())[0]
    apps = ROOT / '.tmp/apps'
    apps.mkdir(parents=True, exist_ok=True)
    archive = apps / editor['archive']
    install.download(editor, archive)
    install.extract(editor, archive, apps / editor['id'])
    trials = [dict(benchmark.trial(editor), repeat=index + 1) for index in range(3)]
    output = ROOT / 'results/control'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'control.json').write_text(json.dumps({
        'editor': editor, 'protocol': benchmark.PROTOCOL,
        'host': {'machine': platform.machine(), 'kernel': platform.release(),
                 'logicalCpuCount': os.cpu_count(),
                 'runUrl': os.environ.get('BENCHMARK_RUN_URL'),
                 'commit': os.environ.get('BENCHMARK_COMMIT')},
        'trials': trials,
    }, indent=2) + '\n')
    if not all(item['valid'] for item in trials):
        raise SystemExit('control opens failed; inspect control.json')


if __name__ == '__main__':
    main()
