(() => {
  'use strict';
  const form = document.getElementById('tendency-filters');
  if (!form) return;
  const status = document.getElementById('update-status');
  const result = document.getElementById('tendency-result');
  const bar = document.getElementById('occupancy-fill');
  const indicator = document.getElementById('occupancy-indicator');
  let controller, serial = 0, busy = false, lastKey = null;
  const number = value => Number(value).toFixed(1);
  const animate = (node, className) => {
    node.classList.remove(className);
    void node.offsetWidth;
    node.classList.add(className);
  };
  async function update(reason = 'selection') {
    if (reason === 'poll' && (busy || document.hidden)) return;
    const current = ++serial;
    if (controller) controller.abort();
    controller = new AbortController();
    const activeController = controller;
    let timedOut = false;
    const timeout = setTimeout(() => { timedOut = true; activeController.abort(); }, 12000);
    busy = true;
    result.setAttribute('aria-busy', 'true');
    if (reason === 'selection') {
      result.classList.add('is-loading');
      document.getElementById('aggregation-details').open = false;
      status.textContent = '読み込み中…';
    }
    const params = new URLSearchParams(new FormData(form));
    params.set('format', 'json');
    const key = params.toString();
    const weekdayLabel = form.elements.weekday.selectedOptions[0].textContent;
    const put = (id, value) => {
      const node = document.getElementById(id);
      if (node.textContent === value) return;
      node.textContent = value;
      if (reason === 'poll' && !result.hidden && lastKey === key) animate(node, 'value-updated');
    };
    try {
      const response = await fetch(`${form.dataset.endpoint}?${params}`, {signal:activeController.signal, headers:{Accept:'application/json'}, cache:'no-store'});
      if (!response.ok) throw new Error('request failed');
      const payload = await response.json();
      if (current !== serial) return;
      const data = payload.result;
      if (!data) throw new Error('missing result');
      const first = result.hidden;
      put('target-location', '対象：' + (/^[0-9０-９]+$/.test(payload.location) ? payload.location + '教室' : payload.location));
      put('selection-label', `${weekdayLabel}・${data.label}　${data.start}〜${data.end}`);
      put('average-count', data.measured ? `約${Math.round(Number(data.average))}人` : 'データなし');
      put('capacity-count', payload.capacity > 0 ? `定員${payload.capacity}人` : '定員未設定');
      result.dataset.state = data.measured ? data.state : 'unknown';
      const rate = data.measured && data.occupancy !== null ? Number(data.occupancy) : null;
      const wasMissing = indicator.hidden;
      indicator.hidden = rate === null;
      const width = `${Math.min(100, Math.max(0, rate ?? 0))}%`;
      result.hidden = false;
      if ((first || wasMissing) && rate !== null) {
        bar.style.transition = 'none';
        bar.style.width = '0%';
        void bar.offsetWidth;
        bar.style.transition = '';
      }
      if (bar.style.width !== width) bar.style.width = width;
      put('occupancy-label', rate === null ? '' : `約${rate > 100 ? rate : Math.round(rate)}％`);
      put('occupancy', `混雑率：${rate !== null ? `${number(rate)}％` : (data.measured ? '算出不可' : 'データなし')}`);
      const labels = {low:'空いている傾向', moderate:'やや混雑する傾向', high:'混雑する傾向'};
      put('state-label', data.measured ? (labels[data.state] || '混雑傾向は算出できません') : 'データなし');
      document.getElementById('state-dot').className = `status-dot ${data.state}`;
      put('data-summary', `対象期間：${payload.start_date}〜${payload.end_date}（日本時間） ／ 計測${data.observed_days}日・${data.samples}件`);
      put('source-summary', [data.contains_dummy ? 'テストデータを含みます' : '', data.contains_unknown ? '記録元未確認のデータを含みます' : ''].filter(Boolean).join(' ／ '));
      document.getElementById('source-summary').hidden = !document.getElementById('source-summary').textContent;
      put('source-detail', `テストデータ：${data.contains_dummy ? '含む' : 'なし'}`);
      if (reason === 'selection' && (first || lastKey !== key)) animate(result, 'result-enter');
      result.classList.remove('is-stale');
      lastKey = key;
      status.textContent = payload.notice || '';
    } catch (error) {
      if (current === serial && (error.name !== 'AbortError' || timedOut)) {
        result.classList.add('is-stale');
        status.textContent = '通信に失敗しました。' + (result.hidden ? '' : '前回の結果です。') + '選び直すと再取得できます。';
      }
    } finally {
      clearTimeout(timeout);
      if (current === serial) {
        busy = false;
        result.setAttribute('aria-busy', 'false');
        result.classList.remove('is-loading');
      }
    }
  }
  result.addEventListener('animationend', event => {
    event.target.classList.remove('result-enter', 'value-updated');
  });
  form.addEventListener('submit', event => event.preventDefault());
  form.addEventListener('change', () => update('selection'));
  window.addEventListener('online', () => update('poll'));
  setInterval(() => update('poll'), 30000);
  update('selection');
})();