/* Manual remote browser (same CloakBrowser persistent context as scheduled watches).
 * One JPEG poll at a time; no CDP socket, cookie values, or page HTML are exposed.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = (window.manualBrowserConfig || {}).api || '/manual-browser/';
  const csrf = (window.manualBrowserConfig || {}).csrf || $('manual-csrf').value;
  const origin = base.replace(/\/$/, '') + '/api/';
  let sid = null, generation = 0, active = true, frameTimer = null, statusTimer = null;
  let lastUrl = null, captureUrl = null, busy = false, dragging = false;
  let viewportWidth = 1366, viewportHeight = 768;
  let inputTail = Promise.resolve();

  const $frame = $('manual-frame');
  const $wrap = $('manual-frame-wrap');
  const $state = $('manual-state');
  const $detail = $('manual-detail');
  function message(msg) { $state.textContent = msg; }
  function controls(on) {
    for (const id of ['manual-refresh','manual-finish','manual-close','manual-type','manual-enter','manual-backspace']) {
      $(id).disabled = !on;
    }
    $('manual-open').disabled = on;
    $('manual-url').readOnly = on;
  }
  async function request(path, data) {
    const response = await fetch(origin + path, {
      method: data ? 'POST' : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'X-CSRFToken': csrf, ...(data ? {'Content-Type':'application/json'} : {}) },
      ...(data ? {body:JSON.stringify(data)} : {}),
    });
    if (!response.ok) {
      let error = `HTTP ${response.status}`;
      try { const t = await response.text(); error = JSON.parse(t).error || t.slice(0, 220) || error; } catch (_) {}
      throw new Error(error);
    }
    return response;
  }
  async function api(path, data) { return (await request(path, data)).json(); }
  function disconnect(reason) {
    sid = null;
    controls(false);
    dragging = false;
    if (frameTimer) clearTimeout(frameTimer);
    if (statusTimer) clearTimeout(statusTimer);
    if (captureUrl) { URL.revokeObjectURL(captureUrl); captureUrl = null; }
    if (reason) message(reason);
  }
  function planFrame() {
    if (sid && active) frameTimer = setTimeout(frame, 600);
  }
  async function frame() {
    if (!sid || !active) return;
    const token = sid;
    try {
      const response = await request('frame?session=' + encodeURIComponent(token));
      const blob = await response.blob();
      if (token !== sid) return;
      const url = URL.createObjectURL(blob);
      const oldUrl = captureUrl;
      captureUrl = url;
      $frame.onload = () => { if (oldUrl) URL.revokeObjectURL(oldUrl); };
      $frame.src = url;
      if (!$frame.onload && oldUrl) URL.revokeObjectURL(oldUrl);
    } catch (e) {
      if (token === sid) { disconnect('画面已断开：' + e.message); }
      return;
    }
    planFrame();
  }
  async function status() {
    if (!sid) return;
    const token = sid;
    try {
      const data = await api('status?session=' + encodeURIComponent(token));
      if (sid !== token) return;
      if (data.generation !== generation) throw new Error('浏览器实例已切换');
      viewportWidth = data.width || viewportWidth;
      viewportHeight = data.height || viewportHeight;
      lastUrl = data.url;
      $detail.textContent = `当前页面：${data.url} | 当前站点 Cookie：${data.cookie_count} 个 | LocalStorage 项：${data.local_storage_keys ?? '未知'} | Profile 锁：${data.profile_lock_held ? '持有' : '未持有'} | 剩余 ${data.seconds_remaining}s` + (data.challenge ? ` | 检测到 ${data.challenge}` : '');
      message(data.challenge ? '检测到验证页面，可由本人按网站要求操作' : '浏览器已连接');
    } catch (e) {
      if (sid === token) disconnect('浏览器状态失效：' + e.message);
      return;
    }
    statusTimer = setTimeout(status, 2500);
  }
  $('manual-open').addEventListener('click', async () => {
    if (sid || busy) return;
    busy = true;
    message('正在打开浏览器…');
    $('manual-open').disabled = true;
    try {
      const data = await api('open', {
        url: $('manual-url').value.trim(), watch_uuid: $('manual-watch-uuid').value.trim()
      });
      sid = data.session;
      generation = data.generation;
      controls(true);
      message('人工操作已连接');
      frame(); status();
    } catch (e) {
      controls(false);
      message('打开失败：' + e.message);
    } finally { busy = false; }
  });
  async function end(path) {
    if (!sid) return;
    const token = sid;
    message('正在关闭会话…');
    try {
      const result = await api(path, {session: token});
      disconnect(result.recheck_queued ? '已关闭人工会话，已加入重新检查队列' : '已关闭人工会话');
      if (path === 'finish' && !$('manual-watch-uuid').value) {
        $detail.textContent = '请返回新增监控页，再点击「前往」刷新静态截图。';
      }
    } catch (e) { message('关闭失败：' + e.message); }
  }
  $('manual-close').addEventListener('click', () => end('close'));
  $('manual-finish').addEventListener('click', () => end('finish'));
  function action(type, args = {}) {
    if (!sid) return Promise.resolve();
    const token = sid;
    // Keep down/move/up and keyboard inputs in request order. Concurrent
    // Flask requests could otherwise release a mouse button before pressing it.
    inputTail = inputTail.catch(() => {}).then(async () => {
      if (sid !== token) return;
      try { await api('action', {session:token, action:type, ...args}); }
      catch (e) { message('操作失败：' + e.message); }
    });
    return inputTail;
  }
  $('manual-refresh').addEventListener('click', () => action('refresh'));
  $('manual-type').addEventListener('click', async () => {
    const input = $('manual-text');
    if (input.value) { await action('text', {text: input.value}); input.value = ''; }
  });
  $('manual-enter').addEventListener('click', () => action('key', {key:'Enter'}));
  $('manual-backspace').addEventListener('click', () => action('key', {key:'Backspace'}));
  function point(event) {
    const rect = $frame.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
    return { x: Math.max(0, Math.min(viewportWidth, (event.clientX - rect.left)*viewportWidth/rect.width)),
             y: Math.max(0, Math.min(viewportHeight, (event.clientY - rect.top)*viewportHeight/rect.height)) };
  }
  $wrap.addEventListener('pointerdown', e => {
    if (!sid || e.button !== 0 || e.target !== $frame) return;
    const p = point(e); if (!p) return;
    e.preventDefault(); $wrap.focus(); dragging = true;
    $wrap.setPointerCapture(e.pointerId);
    action('down', p);
  });
  $wrap.addEventListener('pointermove', e => {
    if (!sid || !dragging) return;
    const p = point(e); if (p) action('move', p);
  });
  $wrap.addEventListener('pointerup', e => {
    if (!dragging) return;
    dragging = false;
    const p = point(e); if (p) action('up', p);
  });
  $wrap.addEventListener('pointercancel', e => {
    if (!dragging) return; dragging = false;
    const p = point(e); if (p) action('up', p);
  });
  $wrap.addEventListener('wheel', e => {
    if (!sid) return;
    e.preventDefault(); const p = point(e);
    if (p) action('scroll', {...p, dx:e.deltaX, dy:e.deltaY});
  }, {passive:false});
  $wrap.addEventListener('keydown', e => {
    if (!sid || e.ctrlKey || e.altKey || e.metaKey) return;
    const allowed = ['Enter','Tab','Escape','Backspace','Delete',' ','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'];
    if (allowed.includes(e.key) || e.key.length === 1) {
      e.preventDefault();
      action('key',{key:e.key === ' ' ? 'Space' : e.key});
    }
  });
  // Avoid a dangling frame stream when hidden; idle expiry still runs server side.
  document.addEventListener('visibilitychange', () => {
    active = !document.hidden;
    if (active && sid) planFrame();
    if (!active && frameTimer) clearTimeout(frameTimer);
  });
  window.addEventListener('pagehide', () => {
    // No reliable asynchronous close on pagehide; server-side idle expiry is authoritative.
    if (frameTimer) clearTimeout(frameTimer);
    if (statusTimer) clearTimeout(statusTimer);
  });
  controls(false);
})();
