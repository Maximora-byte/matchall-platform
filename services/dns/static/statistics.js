(() => {
  const automatic = document.getElementById('stats-auto-refresh');
  const refreshButton = document.getElementById('stats-refresh');
  const status = document.getElementById('stats-refresh-status');
  if (!automatic || !refreshButton || !status) return;
  let busy = false;
  try { automatic.checked = sessionStorage.getItem('dns-statistics-auto') === 'true'; } catch {}
  function remember() {
    try { sessionStorage.setItem('dns-statistics-auto', String(automatic.checked)); } catch {}
  }
  automatic.addEventListener('change', () => {
    remember();
    status.textContent = automatic.checked ? '已开启每 30 秒刷新；后台暂停，操作图表时暂缓更新。' : '自动刷新已关闭。';
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-trace]');
    if (!button) return;
    const show = button.getAttribute('aria-pressed') !== 'true';
    button.setAttribute('aria-pressed', String(show));
    document.querySelectorAll('[data-chart-trace]').forEach(trace => {
      if (trace.dataset.chartTrace === button.dataset.trace) trace.toggleAttribute('hidden', !show);
    });
  });
  async function refresh(manual = false) {
    if (busy || document.hidden || (!manual && !automatic.checked)) return;
    const current = document.getElementById('statistics-data');
    if (!current) return;
    if (!manual && (current.contains(document.activeElement) || String(window.getSelection()).length)) return;
    busy = true; refreshButton.disabled = true; status.textContent = '正在更新统计…';
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(location.href, {credentials: 'same-origin', cache: 'no-store', signal: controller.signal});
      if ([401,403].includes(response.status)) {
        current.replaceChildren(document.createTextNode('登录已失效或权限已变更，请重新登录。'));
        automatic.checked = false; remember();
        throw new Error('auth');
      }
      if (!response.ok) throw new Error('http');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const fresh = doc.getElementById('statistics-data');
      if (!fresh) throw new Error('format');
      const hidden = [...current.querySelectorAll('[data-trace][aria-pressed="false"]')].map(b => b.dataset.trace);
      const opened = [...current.querySelectorAll('details')].map(d => d.open);
      const scroll = [...current.querySelectorAll('.chart-scroll,.stats-table-scroll')].map(d => d.scrollLeft);
      fresh.querySelectorAll('[data-trace]').forEach(b => {
        if (hidden.includes(b.dataset.trace)) b.setAttribute('aria-pressed', 'false');
      });
      fresh.querySelectorAll('[data-chart-trace]').forEach(g => g.toggleAttribute('hidden', hidden.includes(g.dataset.chartTrace)));
      fresh.querySelectorAll('details').forEach((d,i) => d.open = opened[i] || false);
      current.replaceWith(fresh);
      fresh.querySelectorAll('.chart-scroll,.stats-table-scroll').forEach((d,i) => d.scrollLeft = scroll[i] || 0);
      const range = doc.getElementById('stats-range');
      if (range) document.getElementById('stats-range').textContent = range.textContent;
      status.textContent = '已更新 · ' + new Date().toLocaleTimeString() + (automatic.checked ? ' · 每 30 秒刷新' : '');
    } catch (error) {
      status.textContent = error.message === 'auth' ? '登录或权限已变化，请重新登录。' : '更新失败，当前保留上次数据；可稍后重试。';
    } finally {
      clearTimeout(timeout); busy = false; refreshButton.disabled = false;
    }
  }
  refreshButton.addEventListener('click', () => refresh(true));
  setInterval(() => refresh(false), 30000);
})();
