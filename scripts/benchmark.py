"""Measure elapsed time from clicking hello.txt in the editor explorer until it is visible."""
import argparse
import json
import os
from pathlib import Path
import platform
import signal
import socket
import subprocess
import tempfile
import time
from urllib.parse import unquote, urlparse

from cdp import Page

ROOT = Path(__file__).resolve().parent.parent
CONTENT = 'hello world'
TIMEOUT_SECONDS = 15
PROTOCOL = {
    'version': 1,
    'metric': 'elapsed seconds',
    'action': 'single physical-coordinate CDP mouse click on the unique accessible explorer tree item named hello.txt',
    'boundary': 'monotonic clock immediately before the CDP mousePressed/mouseReleased click through the first poll confirming the selected document identity and visible contents',
    'completion': 'selected tab identifies the fixture file and the visible editor text is exactly hello world',
    'observer': 'CDP accessibility tree lookup and 20ms polling plus protocol round trips; click dispatch and observer overhead are included in elapsed time',
    'excluded': 'fixture and workspace preparation, editor launch, profile creation, window readiness, ten-second settling period, and process cleanup',
    'profile': 'fresh HOME, XDG directories and Chromium user-data directory for every trial',
    'cache': 'warm operating-system filesystem caches permitted; application profiles always fresh',
    'repeats': 3,
    'timeoutSeconds': TIMEOUT_SECONDS,
}


def allocate_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def editor_command(editor, home, workspace, port):
    binary = ROOT / '.tmp/apps' / editor['id'] / editor['binary']
    arguments = ['--no-sandbox', '--disable-gpu', '--disable-extensions',
                 '--disable-workspace-trust', '--new-window',
                 f'--user-data-dir={home / "profile"}', f'--remote-debugging-port={port}']
    if editor['id'] == 'vscode':
        arguments.extend(['--ozone-platform=x11', '--skip-welcome', '--skip-release-notes'])
    return [str(binary), *arguments, str(workspace)]


def fixture_matches(editor_id, state, fixture):
    if not isinstance(state, dict) or not isinstance(state.get('identity'), str):
        return False
    identity = state['identity']
    if editor_id == 'lvce':
        identity_path = unquote(urlparse(identity).path) or identity
        identity_matches = identity_path == str(fixture)
    else:
        identity_matches = fixture.name in identity
    return identity_matches and state.get('content') == CONTENT


def trial(editor):
    with tempfile.TemporaryDirectory(prefix='file-open-time-') as temporary:
        root = Path(temporary)
        home = root / 'home'
        workspace = root / 'workspace'
        home.mkdir()
        workspace.mkdir()
        fixture = workspace / 'hello.txt'
        fixture.write_text(CONTENT, encoding='utf-8')
        env = {**os.environ, 'HOME': str(home), 'LC_ALL': 'C',
               'ELECTRON_OZONE_PLATFORM_HINT': 'x11', 'LIBGL_ALWAYS_SOFTWARE': '1',
               'GALLIUM_DRIVER': 'llvmpipe'}
        for key, name in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                          ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state'),
                          ('XDG_RUNTIME_DIR', 'runtime')]:
            env[key] = str(home / name)
            Path(env[key]).mkdir()
        Path(env['XDG_RUNTIME_DIR']).chmod(0o700)
        if 'SUDO_UID' in env:
            uid, gid = int(env['SUDO_UID']), int(env['SUDO_GID'])
            for path in [root, home, workspace, fixture, *home.iterdir()]:
                os.chown(path, uid, gid)

        port = allocate_port()
        command = editor_command(editor, home, workspace, port)
        stdout_path, stderr_path = root / 'stdout', root / 'stderr'
        child = None
        page = None
        stage = 'launch'
        before = None
        click = None
        state = None
        try:
            with stdout_path.open('w') as stdout, stderr_path.open('w') as stderr:
                child = subprocess.Popen(command, cwd=workspace, env=env, stdout=stdout,
                                         stderr=stderr, start_new_session=True)
                stage = 'connect-cdp'
                page = Page(port, timeout=120)
                stage = 'settle'
                time.sleep(10)
                stage = 'read-before-state'
                before = page.document_state(editor['id'])
                if fixture_matches(editor['id'], before, fixture):
                    raise RuntimeError('fixture was already open before the measured explorer click')
                stage = 'click-explorer-item'
                click = page.click_tree_item(fixture.name)
                started = click.pop('started')
                deadline = started + TIMEOUT_SECONDS
                stage = 'wait-for-visible-document'
                while time.monotonic() < deadline:
                    state = page.document_state(editor['id'])
                    if fixture_matches(editor['id'], state, fixture):
                        ended = time.monotonic()
                        return {'valid': True, 'seconds': ended - started,
                                'documentIdentity': state['identity'], 'visibleContent': state['content'],
                                'click': click, 'pollIntervalMs': 20,
                                'timeoutSeconds': TIMEOUT_SECONDS}
                    time.sleep(.02)
                raise TimeoutError(f'open completion not observed within {TIMEOUT_SECONDS}s; last state={state!r}')
        except Exception as error:
            return {'valid': False, 'stage': stage, 'error': str(error), 'command': command,
                    'cdpTarget': page.target_url if page else None,
                    'before': before, 'click': click, 'lastState': state,
                    'stdout': stdout_path.read_text(errors='replace')[-8000:] if stdout_path.exists() else '',
                    'stderr': stderr_path.read_text(errors='replace')[-8000:] if stderr_path.exists() else ''}
        finally:
            if page:
                page.close()
            if child and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor', required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('at least three trials are required')
    editors = json.loads((ROOT / 'config/editors.lock.json').read_text())
    editor = next((entry for entry in editors if entry['id'] == args.editor), None)
    if editor is None:
        parser.error(f'unknown editor {args.editor!r}')
    host = {'machine': platform.machine(), 'kernel': platform.release(),
            'platform': platform.platform(), 'processor': platform.processor(),
            'logicalCpuCount': os.cpu_count(),
            'runUrl': os.environ.get('BENCHMARK_RUN_URL'),
            'commit': os.environ.get('BENCHMARK_COMMIT')}
    trials = [dict(trial(editor), repeat=index + 1) for index in range(args.repeats)]
    Path('results').mkdir(exist_ok=True)
    data = {'editor': editor, 'protocol': PROTOCOL, 'host': host, 'trials': trials}
    Path('results/results.json').write_text(json.dumps(data, indent=2) + '\n')
    if not all(item['valid'] for item in trials):
        raise SystemExit('invalid trials; cannot publish complete report')


if __name__ == '__main__':
    main()
