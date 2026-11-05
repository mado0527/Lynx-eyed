(() => {
  const menu = document.querySelector('[data-screen-menu]');
  if (!menu) return;

  const links = Array.from(menu.querySelectorAll('a.action'));
  const storageKey = 'lynx-eyed:last-screen';
  const pathOf = (link) => new URL(link.href, window.location.href).pathname;
  let selectedPath = null;

  const paintSelection = () => {
    for (const link of links) {
      link.classList.toggle('is-selected', pathOf(link) === selectedPath);
    }
  };

  const restoreSelection = () => {
    try {
      selectedPath = window.sessionStorage.getItem(storageKey);
    } catch {
      // Navigation remains available when browser storage is disabled.
    }
    paintSelection();
  };

  for (const link of links) {
    link.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.ctrlKey ||
          event.metaKey || event.shiftKey || event.altKey) return;
      selectedPath = pathOf(link);
      try {
        window.sessionStorage.setItem(storageKey, selectedPath);
      } catch {
        // Keep the link working even if the selection cannot be stored.
      }
      paintSelection();
    });
  }

  restoreSelection();
  // Browser Back may restore this page without rerunning its scripts.
  window.addEventListener('pageshow', restoreSelection);
})();
