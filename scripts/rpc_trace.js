// Diagnostic-only injection into disposable worker contexts. Never shipped in LVCE.
(() => {
  if (globalThis.__fileOpenRpcTrace) return true;
  const original = MessagePort.prototype.postMessage;
  const ports = new WeakMap();
  let nextPort = 0;
  const mark = (direction, port, data) => {
    if (!data || typeof data !== 'object' || data.jsonrpc !== '2.0') return;
    // Exclude arguments and results: method/id are sufficient to match requests.
    performance.mark('file-open-rpc:' + JSON.stringify({
      direction, port, id: data.id, method: data.method || '',
    }));
  };
  MessagePort.prototype.postMessage = function (...args) {
    let port = ports.get(this);
    if (!port) {
      port = ++nextPort;
      ports.set(this, port);
      this.addEventListener('message', event => mark('receive', port, event.data));
    }
    mark('send', port, args[0]);
    return Reflect.apply(original, this, args);
  };
  globalThis.__fileOpenRpcTrace = true;
  return true;
})()
