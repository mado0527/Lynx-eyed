// Fetch server-rendered values; all aggregation and forecast calculations stay on the server.
(() => {
  'use strict';
  const root = document.querySelector('[data-live-page]');
  if (!root) return;
  const fragments = new Map([...root.querySelectorAll('[data-live-fragment]')].map(node =>
    [node.dataset.liveFragment, {node, html:node.outerHTML, pending:null}]));
  const status = document.createElement('p');
  status.className = 'live-update-status';
  status.setAttribute('role', 'status');
  status.setAttribute('aria-live', 'polite');
  root.querySelector('header').after(status);
  let serial = 0, controller, busy = false;
  let url = new URL(window.location.href);
  function applyFragments() {
    let changed = false;
    for (const entry of fragments.values()) {
      const next = entry.pending;
      if (!next || entry.node.contains(document.activeElement)) continue;
      const opened = [...entry.node.querySelectorAll('details')].map(node => node.open);
      const replacement = next.cloneNode(true);
      [...replacement.querySelectorAll('details')].forEach((node, i) => { node.open = opened[i] ?? node.open; });
      entry.node.replaceWith(replacement);
      entry.node = replacement;
      entry.html = next.outerHTML;
      entry.pending = null;
      changed = true;
    }
    if (changed) document.dispatchEvent(new Event('lynx:content-updated'));
  }
  document.addEventListener('focusout', () => queueMicrotask(applyFragments));
  async function update(manual = false) {
    if (!manual && (busy || document.hidden)) return;
    const current = ++serial;
    controller?.abort();
    controller = new AbortController();
    const activeController = controller;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; activeController.abort(); }, 12000);
    busy = true;
    root.setAttribute('aria-busy', 'true');
    if (manual) status.textContent = '更新中…';
    try {
      const response = await fetch(url, {signal:activeController.signal, cache:'no-store',
        headers:{Accept:'text/html', 'X-Requested-With':'XMLHttpRequest'}});
      if (!response.ok) throw new Error('request failed');
      const documentCopy = new DOMParser().parseFromString(await response.text(), 'text/html');
      if (current !== serial) return;
      const nextRoot = documentCopy.querySelector('[data-live-page]');
      if (nextRoot?.dataset.livePage !== root.dataset.livePage) throw new Error('unexpected response');
      // Validate the whole response before changing any displayed values.
      const incoming = new Map();
      for (const [key] of fragments) {
        const node = nextRoot.querySelector(`[data-live-fragment="${key}"]`);
        if (!node) throw new Error('missing fragment');
        incoming.set(key, node);
      }
      for (const [key, entry] of fragments) {
        const node = incoming.get(key);
        entry.pending = entry.html === node.outerHTML ? null : node;
      }
      applyFragments();
      status.textContent = manual ? '更新しました' : '';
      if (manual) history.replaceState(null, '', url);
    } catch (error) {
      if (current === serial && (error.name !== 'AbortError' || timedOut))
        status.textContent = '通信に失敗しました。前回の表示を保持しています。次回の取得で再試行します。';
    } finally {
      clearTimeout(timeout);
      if (current === serial) { busy = false; root.setAttribute('aria-busy', 'false'); }
    }
  }
  const form = document.getElementById('location-form');
  form?.addEventListener('submit', event => {
    event.preventDefault();
    url = new URL(window.location.href);
    for (const [key, value] of new FormData(form)) url.searchParams.set(key, value);
    update(true);
  });
  window.addEventListener('online', () => update(false));
  const seconds = Number(root.dataset.liveInterval);
  if (seconds > 0) setInterval(() => update(false), seconds * 1000);
})();