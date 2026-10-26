// Diagnostic-only observer in the disposable page. Never shipped or used by protocol v1.
(fixturePath => {
  const entries = [];
  let dropped = 0;
  let previous = '';
  let observations = 0;
  let totalObserverMs = 0;
  let maxObserverMs = 0;
  const snapshot = reason => {
    const started = performance.now();
    const identity = document.querySelector('.MainTabSelected')?.getAttribute('title') || '';
    const editor = document.querySelector('.EditorContent') || document.querySelector('.Editor');
    const content = editor?.innerText ?? '';
    const active = document.activeElement;
    const focused = !!active?.matches('[name="editor"]');
    let path;
    try { path = decodeURIComponent(new URL(identity).pathname); } catch { path = identity; }
    const exact = path === fixturePath && content.replaceAll('\u00a0', ' ') === 'hello world';
    const state = JSON.stringify({ identity, content, focused });
    const duration = performance.now() - started;
    observations++;
    totalObserverMs += duration;
    maxObserverMs = Math.max(maxObserverMs, duration);
    if (reason === 'mutation' && state === previous) return;
    previous = state;
    const entry = { reason, now: started, observerDuration: duration,
      identity, content, exact, focused, activeTag: active?.tagName,
      activeName: active?.getAttribute('name') };
    if (entries.length >= 256) { dropped++; return; }
    entries.push(entry);
    performance.mark('file-open-dom:' + JSON.stringify(entry));
  };
  const observer = new MutationObserver(() => snapshot('mutation'));
  observer.observe(document.body, { subtree: true, childList: true, characterData: true,
    attributes: true, attributeFilter: ['title', 'class', 'style'] });
  for (const event of ['mousedown', 'mouseup', 'focusin']) {
    document.addEventListener(event, () => snapshot(event), true);
  }
  globalThis.__fileOpenDomTrace = () => ({ entries, dropped, observations, totalObserverMs, maxObserverMs, timeOrigin: performance.timeOrigin,
    now: performance.now() });
  snapshot('installed');
  return true;
})
