(() => {
  let notice = null;
  const update = () => {
    if (navigator.onLine === false) {
      if (!notice) {
        notice = document.createElement('p');
        notice.className = 'communication-error';
        notice.setAttribute('role', 'alert');
        notice.textContent = 'エラーが発生しました';
        document.body.appendChild(notice);
      }
    } else if (notice) {
      notice.remove();
      notice = null;
    }
  };
  window.addEventListener('offline', update);
  window.addEventListener('online', update);
  window.addEventListener('pageshow', update);
  // Keep the current page visible when submitting a form while offline.
  document.addEventListener('submit', (event) => {
    if (navigator.onLine === false) {
      event.preventDefault();
      update();
    }
  });
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href]');
    if (!link || navigator.onLine !== false) return;
    const url = new URL(link.href, window.location.href);
    if (!['http:', 'https:'].includes(url.protocol) ||
        (url.origin === window.location.origin &&
         url.pathname === window.location.pathname &&
         url.search === window.location.search && url.hash)) return;
    event.preventDefault();
    update();
  });
  update();
})();
