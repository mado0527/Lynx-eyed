// Display existing chart values only. No predictions or aggregates are generated here.
document.querySelectorAll('.plot, .trend-tooltip-plot').forEach((plot, index) => {
  // A stale or missing stylesheet must not render tooltip text as normal page content.
  if (getComputedStyle(plot).getPropertyValue('--graph-tooltip-styled').trim() !== '1') return;
  const columns = [...plot.querySelectorAll('.column')];
  const targets = columns.length ? columns : [...plot.querySelectorAll('.chart-dot')];
  if (!targets.length) return;
  plot.classList.add('tooltip-ready');
  const tooltip = document.createElement('div');
  tooltip.className = 'graph-tooltip';
  tooltip.id = `graph-tooltip-${index}`;
  tooltip.setAttribute('role', 'tooltip');
  tooltip.hidden = true;
  const guide = document.createElement('div');
  guide.className = 'tooltip-guide';
  guide.hidden = true;
  guide.setAttribute('aria-hidden', 'true');
  plot.append(guide, tooltip);
  let active = null;
  let pinned = false;
  function hide() {
    active?.classList.remove('is-active');
    active?.removeAttribute('aria-describedby');
    active = null;
    tooltip.hidden = guide.hidden = true;
    pinned = false;
  }
  function show(target, pointerY) {
    const source = target.querySelector(columns.length ? '.column-tooltip' : '.tooltip');
    if (!source && !target.dataset.tooltipHeading) return;
    active?.classList.remove('is-active');
    active?.removeAttribute('aria-describedby');
    active = target;
    active.classList.add('is-active');
    active.setAttribute('aria-describedby', tooltip.id);
    if (source) {
      tooltip.replaceChildren(...[...source.childNodes].map(node => node.cloneNode(true)));
    } else {
      const heading = document.createElement('span');
      heading.className = 'tooltip-heading';
      heading.textContent = target.dataset.tooltipHeading;
      const value = document.createElement('span');
      value.className = 'tooltip-value';
      value.textContent = target.dataset.tooltipValue;
      tooltip.replaceChildren(heading, value);
    }
    tooltip.classList.toggle('actual-tooltip', target.classList.contains('actual-dot'));
    tooltip.hidden = false;
    const bounds = plot.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    const x = rect.left + rect.width / 2 - bounds.left;
    const y = columns.length ? (pointerY ?? bounds.height / 2) : rect.top + rect.height / 2 - bounds.top;
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    tooltip.style.left = `${Math.max(4, Math.min(x + 12, bounds.width - width - 4))}px`;
    tooltip.style.top = `${Math.max(4, Math.min(y + 12, bounds.height - height - 4))}px`;
    guide.hidden = !!columns.length;
    guide.style.left = `${x}px`;
  }
  function nearest(event) {
    return targets.reduce((best, target) => {
      const rect = target.getBoundingClientRect();
      const dx = Math.abs(event.clientX - rect.left - rect.width / 2);
      const dy = Math.abs(event.clientY - rect.top - rect.height / 2);
      const distance = dx + (columns.length ? 0 : dy * 0.001);
      return !best || distance < best.distance ? { target, distance } : best;
    }, null).target;
  }
  plot.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch' || pinned) return;
    show(nearest(event), event.clientY - plot.getBoundingClientRect().top);
  });
  plot.addEventListener('pointerleave', () => {
    if (!pinned && !plot.contains(document.activeElement)) hide();
  });
  plot.addEventListener('click', event => {
    pinned = true;
    show(nearest(event), event.clientY - plot.getBoundingClientRect().top);
  });
  targets.forEach(target => target.addEventListener('focus', () => show(target)));
  plot.addEventListener('focusout', event => {
    if (!plot.contains(event.relatedTarget)) hide();
  });
  document.addEventListener('pointerdown', event => {
    if (!plot.contains(event.target)) hide();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') hide();
  });
});
