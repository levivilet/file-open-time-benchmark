// Diagnostic-only causal experiment: remove frame waits in one disposable worker.
// Synthetic eligibility timestamps also bypass its 16ms frame throttle. All
// measured durations and trace marks still use the real performance clock.
(() => {
  if (!location.href.includes('/renderer-worker/')) return false;
  let timestamp = performance.now();
  let nextId = 0;
  const timers = new Map();
  const originalCancel = globalThis.cancelAnimationFrame.bind(globalThis);
  globalThis.requestAnimationFrame = callback => {
    const id = --nextId;
    const timer = setTimeout(() => {
      timers.delete(id);
      timestamp = Math.max(timestamp + 17, performance.now());
      performance.mark('file-open-ablation:immediate-frame');
      callback(timestamp);
    }, 0);
    timers.set(id, timer);
    return id;
  };
  globalThis.cancelAnimationFrame = id => {
    if (timers.has(id)) {
      clearTimeout(timers.get(id));
      timers.delete(id);
    } else originalCancel(id);
  };
  return true;
})()
