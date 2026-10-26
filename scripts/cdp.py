"""Small CDP client for real explorer clicks and visible-document checks."""
import base64
import json
from pathlib import Path
import time
import urllib.request


class Page:
    def __init__(self, port, timeout=60):
        import websocket

        deadline = time.monotonic() + timeout
        while True:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=2) as response:
                    targets = json.load(response)
                target = next(t for t in targets if t['type'] == 'page' and
                              not t['url'].startswith('devtools:'))
                self.target_url = target['url']
                self.socket = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=30,
                                                           suppress_origin=True)
                self.counter = 0
                self.events = []
                self.timings = None
                self.call('Page.enable')
                self.call('Runtime.enable')
                self.call('Accessibility.enable')
                return
            except (OSError, StopIteration):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Editor never exposed a page over CDP')
                time.sleep(.25)

    def call(self, method, session_id=None, **params):
        started = time.monotonic() if self.timings is not None else None
        self.counter += 1
        request = {'id': self.counter, 'method': method, 'params': params}
        if session_id is not None:
            request['sessionId'] = session_id
        self.socket.send(json.dumps(request))
        while True:
            message = json.loads(self.socket.recv())
            if message.get('id') == self.counter:
                if 'error' in message:
                    raise RuntimeError(message['error'])
                if self.timings is not None:
                    self.timings.append({'method': method, 'started': started,
                                         'ended': time.monotonic()})
                return message['result']
            if message.get('method') in ('Tracing.tracingComplete', 'Target.attachedToTarget'):
                self.events.append(message)

    def wait_event(self, method):
        while True:
            for index, event in enumerate(self.events):
                if event.get('method') == method:
                    return self.events.pop(index)['params']
            self.events.append(json.loads(self.socket.recv()))

    def start_trace(self):
        self.call('Target.setAutoAttach', autoAttach=True, waitForDebuggerOnStart=False,
                  flatten=True)
        workers = [event['params'] for event in self.events
                   if event.get('method') == 'Target.attachedToTarget'
                   and event['params']['targetInfo']['type'] == 'worker']
        expression = Path(__file__).with_name('rpc_trace.js').read_text()
        self.traced_workers = []
        for worker in workers:
            result = self.call('Runtime.evaluate', session_id=worker['sessionId'],
                               expression=expression, returnByValue=True)
            if result.get('exceptionDetails') or result.get('result', {}).get('value') is not True:
                raise RuntimeError(f'RPC trace injection failed: {worker["targetInfo"]["url"]}')
            self.traced_workers.append(worker['targetInfo']['url'])
        if not self.traced_workers:
            raise RuntimeError('no existing workers attached for RPC tracing')
        self.evaluate(expression)
        self.call('Tracing.start', transferMode='ReturnAsStream',
                  categories='toplevel,devtools.timeline,blink.user_timing,'
                             'disabled-by-default-devtools.timeline')
        self.timings = []

    def start_dom_observer(self, fixture):
        expression = Path(__file__).with_name('dom_trace.js').read_text()
        if self.evaluate(f'({expression})({json.dumps(str(fixture))})') is not True:
            raise RuntimeError('DOM observer injection failed')
        if self.timings is None:
            self.timings = []

    def dom_observations(self):
        # Keep observing after the original completion boundary to capture later focus/commits.
        return self.evaluate('new Promise(resolve => setTimeout(() => '
                             'resolve(globalThis.__fileOpenDomTrace()), 250))')

    def stop_trace(self, destination):
        self.call('Tracing.end')
        complete = self.wait_event('Tracing.tracingComplete')
        stream = complete['stream']
        try:
            with destination.open('wb') as output:
                while True:
                    chunk = self.call('IO.read', handle=stream, size=1048576)
                    data = chunk.get('data', '')
                    output.write(base64.b64decode(data) if chunk.get('base64Encoded')
                                 else data.encode())
                    if chunk.get('eof'):
                        break
        finally:
            self.call('IO.close', handle=stream)
        if complete.get('dataLossOccurred'):
            raise RuntimeError('diagnostic trace lost events')

    def evaluate(self, expression):
        result = self.call('Runtime.evaluate', expression=expression, returnByValue=True,
                           awaitPromise=True)
        if result.get('exceptionDetails'):
            raise RuntimeError(result['exceptionDetails'])
        return result['result'].get('value')

    def click_tree_item(self, label):
        tree = self.call('Accessibility.getFullAXTree')['nodes']
        matches = [node for node in tree if node.get('role', {}).get('value') == 'treeitem' and
                   node.get('name', {}).get('value') == label and node.get('backendDOMNodeId')]
        if len(matches) != 1:
            raise RuntimeError(f'expected one visible explorer tree item named {label!r}; found {len(matches)}')
        model = self.call('DOM.getBoxModel', backendNodeId=matches[0]['backendDOMNodeId'])
        quad = model['model']['border']
        x = sum(quad[0::2]) / 4
        y = sum(quad[1::2]) / 4
        viewport = self.call('Page.getLayoutMetrics')['cssVisualViewport']
        if not (0 <= x < viewport['clientWidth'] and 0 <= y < viewport['clientHeight']):
            raise RuntimeError(f'explorer item is outside the visible viewport: ({x}, {y})')
        self.call('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
        started = time.monotonic()
        self.call('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y, button='left', clickCount=1)
        self.call('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y, button='left', clickCount=1)
        return {'role': 'treeitem', 'name': label, 'x': x, 'y': y, 'started': started}

    def document_state(self, editor_id):
        if editor_id == 'lvce':
            expression = """(() => ({
              identity: document.querySelector('.MainTabSelected')?.getAttribute('title') || '',
              content: document.querySelector('.EditorContent')?.innerText ??
                document.querySelector('.Editor')?.innerText ?? ''
            }))()"""
        else:
            expression = """(() => ({
              identity: document.querySelector('.monaco-workbench .tabs-container .tab.active')?.getAttribute('aria-label') || '',
              content: document.querySelector('.monaco-editor .view-lines')?.innerText || ''
            }))()"""
        return self.evaluate(expression)

    def close(self):
        self.socket.close()
