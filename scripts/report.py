"""Validate complete editor artifacts and create the static comparison site."""
import argparse
import html
import json
import math
from pathlib import Path
import statistics

from benchmark import CONTENT, PROTOCOL

ROOT = Path(__file__).resolve().parent.parent
EDITORS = json.loads((ROOT / 'config/editors.lock.json').read_text())


def validate_result(data, editor_id):
    if not isinstance(data, dict) or not isinstance(data.get('editor'), dict) or data['editor'].get('id') != editor_id:
        raise ValueError(f'{editor_id}: result has the wrong editor identity')
    if data.get('protocol') != PROTOCOL:
        raise ValueError(f'{editor_id}: incompatible result protocol')
    trials = data.get('trials')
    if not isinstance(trials, list) or len(trials) < PROTOCOL['repeats']:
        raise ValueError(f'{editor_id}: fewer than {PROTOCOL["repeats"]} trials')
    for index, trial in enumerate(trials, 1):
        if not isinstance(trial, dict) or trial.get('valid') is not True:
            raise ValueError(f'{editor_id}: trial {index} is invalid')
        seconds = trial.get('seconds')
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds):
            raise ValueError(f'{editor_id}: trial {index} has an invalid duration')
        if seconds <= 0 or seconds >= PROTOCOL['timeoutSeconds']:
            raise ValueError(f'{editor_id}: trial {index} duration is out of range')
        content = trial.get('visibleContent')
        if not isinstance(content, str) or content != CONTENT:
            raise ValueError(f'{editor_id}: trial {index} does not show the expected content')
        identity = trial.get('documentIdentity', '')
        if not isinstance(identity, str) or 'hello.txt' not in identity:
            raise ValueError(f'{editor_id}: trial {index} identifies the wrong document')
        repeat = trial.get('repeat')
        if isinstance(repeat, bool) or repeat != index:
            raise ValueError(f'{editor_id}: trial {index} has an invalid repeat number')
    if not isinstance(data.get('host'), dict) or data['host'].get('machine') not in ('aarch64', 'arm64'):
        raise ValueError(f'{editor_id}: result is missing ARM64 host metadata')
    return data


def load_results(results_root):
    found = {}
    for path in results_root.glob('open-*/results.json'):
        try:
            data = json.loads(path.read_text())
            editor_id = data['editor']['id']
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ValueError(f'malformed benchmark artifact {path}: {error}') from error
        if path.parent.name != f'open-{editor_id}' or editor_id in found:
            raise ValueError(f'misnamed or duplicate benchmark artifact for {editor_id}')
        found[editor_id] = path
    expected = {editor['id'] for editor in EDITORS}
    if found.keys() != expected:
        raise ValueError(f'editor artifacts do not match matrix (missing: {sorted(expected - found.keys())}; '
                         f'extra: {sorted(found.keys() - expected)})')
    results = []
    for editor in EDITORS:
        data = validate_result(json.loads(found[editor['id']].read_text()), editor['id'])
        if data['editor'] != editor:
            raise ValueError(f"{editor['id']}: version does not match the pinned editor matrix")
        results.append({'editor': editor, 'data': data})
    return results


def build_report(results, output, run_url, commit):
    output.mkdir(parents=True, exist_ok=True)
    raw = output / 'raw'
    raw.mkdir(exist_ok=True)
    entries, rows, bars = [], [], []
    for item in sorted(results, key=lambda value: statistics.median(
            trial['seconds'] for trial in value['data']['trials'])):
        editor, data = item['editor'], item['data']
        values = [trial['seconds'] for trial in data['trials']]
        median = statistics.median(values)
        filename = f"{editor['id']}.json"
        (raw / filename).write_text(json.dumps(data, indent=2) + '\n')
        entry = {'id': editor['id'], 'name': editor['name'], 'version': editor['version'],
                 'medianSeconds': median, 'trials': [{'repeat': trial['repeat'], 'seconds': trial['seconds']}
                                                       for trial in data['trials']],
                 'protocol': data['protocol'], 'host': data['host'], 'raw': f'raw/{filename}'}
        entries.append(entry)
        trial_values = '<br>'.join(f'{value:.3f}s' for value in values)
        rows.append(f"<tr><th scope='row'>{html.escape(editor['name'])}</th>"
                    f"<td>{html.escape(editor['version'])}</td><td>{median:.3f}s</td>"
                    f"<td>{trial_values}</td><td><a href='raw/{html.escape(filename)}' download>Raw JSON</a></td></tr>")

    report = {'complete': True, 'runUrl': run_url, 'commit': commit, 'unit': 'seconds',
              'protocol': PROTOCOL, 'editors': entries}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    maximum = max(entry['medianSeconds'] for entry in entries)
    chart_max = maximum * 1.2 or 1
    for index, entry in enumerate(entries):
        x = 180 + index * 420
        height = 230 * entry['medianSeconds'] / chart_max
        bars.append(f"<g><rect x='{x}' y='{270 - height:.1f}' width='150' height='{height:.1f}'/>")
        bars.append(f"<text x='{x + 75}' y='300' text-anchor='middle'>{html.escape(entry['name'])}</text>")
        bars.append(f"<text x='{x + 75}' y='{258 - height:.1f}' text-anchor='middle'>{entry['medianSeconds']:.3f}s</text></g>")
    safe_run, safe_commit = html.escape(run_url, quote=True), html.escape(commit)
    page = f"""<!doctype html>
<html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>File-open time benchmark</title><style>
:root{{font:16px/1.5 system-ui,sans-serif;color:#17212b;background:#f4f7fa}}body{{max-width:1000px;margin:3rem auto;padding:0 1rem}}
.note{{padding:1rem;background:#e8f1fa;border-radius:.5rem}}table{{border-collapse:collapse;width:100%;background:white;margin:1.5rem 0}}
th,td{{padding:.7rem;border-bottom:1px solid #d7e0e8;text-align:left}}th{{background:#e8f1fa}}a{{color:#0759a5}}
svg{{width:100%;max-width:900px;background:white}}rect{{fill:#2477ae}}text{{font:14px system-ui,sans-serif;fill:#17212b}}
</style></head><body><main><h1>File-open time benchmark</h1>
<p>Latest complete run: <a href='{safe_run}'>GitHub Actions</a> · commit <code>{safe_commit}</code></p>
<p class='note'>Each trial starts with a fresh editor profile and a workspace containing <code>hello.txt</code> with the exact text <code>hello world</code>. After launch and a ten-second settling period, the benchmark uses a real CDP mouse click on the accessible Explorer tree item. Timing starts immediately before the click and ends when polling confirms that the selected document is <code>hello.txt</code> and the visible editor content matches. Launch, workspace setup and cleanup are excluded. The click dispatch and observation polling overhead are included. Three or more trials are run per pinned editor; the chart compares medians and the table exposes each duration and downloadable raw evidence.</p>
<p>All {len(entries)} required editors completed with valid measurements. Durations are elapsed seconds; lower values indicate a faster observed open.</p>
<svg viewBox='0 0 900 340' role='img' aria-label='Median seconds from Explorer click until file content is visible'>{''.join(bars)}</svg>
<table><thead><tr><th>Editor</th><th>Version</th><th>Median open time</th><th>Trial durations</th><th>Evidence</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table><p><a href='report.json'>Complete report and protocol</a></p></main></body></html>"""
    (output / 'index.html').write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'results/editors')
    parser.add_argument('--output', type=Path, default=ROOT / '.tmp/pages')
    parser.add_argument('--run-url', default='')
    parser.add_argument('--commit', default='')
    args = parser.parse_args()
    results = load_results(args.input)
    build_report(results, args.output, args.run_url, args.commit)
    print(f'Built a complete report for {len(results)} editors at {args.output}')


if __name__ == '__main__':
    main()
