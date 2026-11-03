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
  let inputTail = Promise.resolve(), addressDirty = false, navigating = false;
  let currentUrl = null, currentSession = null, pointerPending = null, pointerSending = false;
  let frameFailures = 0, statusFailures = 0;
  let layoutTimer = null, viewportTail = Promise.resolve(), viewportApplied = '';
  const root = $('manual-browser-root');
  const requestedUrl = $('manual-url').value.trim();
  const requestedWatch = $('manual-watch-uuid').value.trim();
  function cover(text) {
    $('manual-cover').textContent = text;
    $('manual-cover').hidden = false;
    $frame.hidden = true;
  }

  const $frame = $('manual-frame');
  const $wrap = $('manual-frame-wrap');
  const $state = $('manual-state');
  const $detail = $('manual-detail');
  function message(msg) { $state.textContent = msg; }
  function controls(on) {
    for (const id of ['manual-refresh','manual-finish','manual-close','manual-type','manual-enter','manual-backspace','manual-go','manual-back','manual-forward']) {
      $(id).disabled = !on;
    }
    $('manual-open').disabled = on;
    $('manual-url').readOnly = false;
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
    $('manual-connection').textContent = '○ 未连接';
    $('manual-site-data').textContent = '';
    $('manual-remaining').textContent = '';
    frameFailures = 0; statusFailures = 0;
    viewportApplied = '';
    cover('会话已结束，可重新连接。');
  }
  function planFrame() {
    if (sid && active && !navigating) frameTimer = setTimeout(frame, 400);
  }
  async function frame() {
    if (!sid || !active || navigating) return;
    const token = sid;
    try {
      const response = await request('frame?session=' + encodeURIComponent(token));
      const blob = await response.blob();
      frameFailures = 0;
      if (token !== sid || navigating) return;
      const url = URL.createObjectURL(blob);
      const oldUrl = captureUrl;
      captureUrl = url;
      $frame.onload = () => { if (oldUrl) URL.revokeObjectURL(oldUrl); };
      $frame.src = url;
      $frame.hidden = false;
      $('manual-cover').hidden = true;
      if (!$frame.onload && oldUrl) URL.revokeObjectURL(oldUrl);
    } catch (e) {
      if (token !== sid) return;
      // A navigation may cause HTTP 500 or a screenshot timeout.
      // Do not confuse one failed frame with a closed browser session.
      if (/HTTP (400|401|403|404|409)\b/.test(e.message)) {
        disconnect('会话权限或状态已失效：' + e.message);
        inspectSession();
        return;
      }
      frameFailures++;
      message(`画面暂时不可用，正在重试 (${frameFailures})：${e.message}`);
      frameTimer = setTimeout(frame, Math.min(5000, frameFailures * 800));
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
      statusFailures = 0;
      viewportWidth = data.width || viewportWidth;
      viewportHeight = data.height || viewportHeight;
      lastUrl = data.url;
      currentUrl = data.url;
      if (!addressDirty && document.activeElement !== $('manual-url')) $('manual-url').value = data.url;
      $('manual-connection').textContent = data.challenge ? `● 验证页面：${data.challenge}` : '● 已连接';
      $('manual-site-data').textContent = `Cookie：${data.cookie_count} | LocalStorage：${data.local_storage_keys ?? '未知'}`;
      $('manual-remaining').textContent = `空闲剩余 ${Math.floor(data.seconds_remaining / 60)}:${String(data.seconds_remaining % 60).padStart(2, '0')}`;
      $detail.textContent = `实际网址：${data.url} | Profile 锁：${data.profile_lock_held ? '持有' : '未持有'} | 浏览器代次：${data.generation}`;
      message(data.challenge ? '页面仍要求验证，可继续人工操作' : '浏览器已连接');
    } catch (e) {
      if (sid !== token) return;
      if (/HTTP (400|401|403|404|409)\b|浏览器实例已切换/.test(e.message)) {
        disconnect('会话已失效：' + e.message);
        inspectSession();
        return;
      }
      statusFailures++;
      message(`状态暂时不可用，正在重试 (${statusFailures})：${e.message}`);
      statusTimer = setTimeout(status, Math.min(7000, statusFailures * 1500));
      return;
    }
    statusTimer = setTimeout(status, 2500);
  }
  $('manual-open').addEventListener('click', async () => {
    if (sid || busy) return;
    const destination = $('manual-url').value.trim();
    if (!destination && !$('manual-watch-uuid').value.trim()) {
      message('请先在地址栏输入网址，再连接共享浏览器。');
      $('manual-url').focus();
      return;
    }
    busy = true;
    message('正在打开浏览器…');
    $('manual-open').disabled = true;
    try {
      const data = await api('open', {
        url: destination, watch_uuid: $('manual-watch-uuid').value.trim()
      });
      sid = data.session;
      generation = data.generation;
      controls(true);
      message('人工操作已连接');
      await syncViewport();
      currentSession = null;
      $('manual-existing').hidden = true;
      $('manual-connection').textContent = '● 已连接';
      cover('正在获取实时画面…');
      addressDirty = false;
      frame(); status();
    } catch (e) {
      controls(false);
      message('打开失败：' + e.message);
      await inspectSession();
    } finally { busy = false; }
  });
  async function end(path) {
    if (!sid) return;
    const token = sid;
    message('正在关闭会话…');
    try {
      const result = await api(path, {session: token});
      disconnect(result.recheck_queued ? '已关闭人工会话，已加入重新检查队列' : '已关闭人工会话');
      await inspectSession();
      if (path === 'finish' && !$('manual-watch-uuid').value) {
        $detail.textContent = '请返回新增监控页，再点击「前往」刷新静态截图。';
      }
    } catch (e) { message('关闭失败：' + e.message); }
  }
  $('manual-close').addEventListener('click', () => end('close'));
  $('manual-finish').addEventListener('click', () => end('finish'));
  function action(type, args = {}, mustSucceed = false) {
    if (!sid) return Promise.resolve();
    const token = sid;
    // Keep input ordering; propagate navigation errors to its caller.
    const next = inputTail.catch(() => {}).then(() => {
      if (sid !== token) return;
      return api('action', {session:token, action:type, ...args});
    });
    inputTail = next.catch(e => { message('操作失败：' + e.message); });
    return mustSucceed ? next : inputTail;
  }
  $('manual-refresh').addEventListener('click', async () => {
    if (!sid || navigating) return;
    navigating = true;
    if (frameTimer) clearTimeout(frameTimer);
    cover('正在刷新页面…');
    try { await action('refresh', {}, true); message('已刷新页面'); }
    catch (e) { message('刷新失败：' + e.message); }
    finally { navigating = false; if (sid && active) frameTimer = setTimeout(frame, 0); }
  });
  $('manual-type').addEventListener('click', async () => {
    const input = $('manual-text');
    if (input.value) { await action('text', {text: input.value}); input.value = ''; }
  });
  $('manual-enter').addEventListener('click', () => action('key', {key:'Enter'}));
  $('manual-backspace').addEventListener('click', () => action('key', {key:'Backspace'}));
  function point(event) {
    // The <img> uses intrinsic aspect ratio (max-width/max-height), not
    // object-fit letterboxing, so its bounding box equals actual pixels.
    const rect = $frame.getBoundingClientRect();
    if ($frame.hidden || !rect.width || !rect.height) return null;
    if (event.clientX < rect.left || event.clientX > rect.right ||
        event.clientY < rect.top || event.clientY > rect.bottom) return null;
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
  async function flushMoves() {
    if (pointerSending) return;
    pointerSending = true;
    try {
      while (sid && dragging && pointerPending) {
        const pointToSend = pointerPending;
        pointerPending = null;
        await action('move', pointToSend);
      }
    } finally { pointerSending = false; }
  }
  $wrap.addEventListener('pointermove', e => {
    if (!sid || !dragging) return;
    const p = point(e);
    if (p) { pointerPending = p; flushMoves(); }
  });
  $wrap.addEventListener('pointerup', e => {
    if (!dragging) return;
    dragging = false;
    const p = point(e) || pointerPending;
    pointerPending = null;
    if (p) action('up', p);
  });
  $wrap.addEventListener('pointercancel', e => {
    if (!dragging) return; dragging = false;
    const p = point(e) || pointerPending;
    pointerPending = null;
    if (p) action('up', p);
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

  async function inspectSession() {
    try {
      const d = await api('current');
      currentSession = d.active ? d : null;
      const box = $('manual-existing');
      box.hidden = !d.active && !d.opening;
      $('manual-resume').hidden = !d.active || !d.owned;
      $('manual-switch').hidden = !d.active || !d.owned;
      if (d.active) {
        $('manual-existing-title').textContent = d.owned ? '已有你的人工操作会话' : '其他登录用户正在使用人工浏览器';
        $('manual-existing-description').textContent =
          (d.owned ? d.url : '当前网页信息仅本人可见') + ` · 剩余约 ${Math.ceil(d.seconds_remaining / 60)} 分钟`;
        $('manual-open').disabled = true;
      } else if (d.opening) {
        $('manual-existing-title').textContent = '已有会话正在创建或清理，请稍后刷新';
        $('manual-existing-description').textContent = '';
        $('manual-open').disabled = true;
      } else if (!sid) {
        controls(false);
      }
    } catch(e) { message('查询会话失败：' + e.message); }
  }
  $('manual-check').addEventListener('click', inspectSession);
  $('manual-resume').addEventListener('click', async () => {
    if (!currentSession || !currentSession.owned) return;
    try {
      const d = await api('resume', {session:currentSession.session});
      // The old tab's previous token is revoked by the server.
      sid = d.session; generation = d.generation;
      controls(true);
      await syncViewport();
      $('manual-existing').hidden = true;
      currentSession = null;
      message('已恢复之前的人工会话');
      cover('正在同步当前页面…');
      frame(); status();
    } catch (e) { message('恢复失败：' + e.message); await inspectSession(); }
  });
  $('manual-switch').addEventListener('click', async () => {
    if (!currentSession || !currentSession.owned) return;
    if (!window.confirm('关闭已有人工会话并打开当前网站？旧页面尚未保存的输入可能丢失。')) return;
    try {
      await api('close', {session:currentSession.session});
      currentSession = null;
      $('manual-existing').hidden = true;
      $('manual-url').value = requestedUrl;
      addressDirty = false;
      controls(false);
      $('manual-open').click();
    } catch (e) { message('切换失败：' + e.message); await inspectSession(); }
  });
  async function navigatePage(value) {
    if (!sid || navigating) return;
    let url = value.trim();
    if (!/^https?:\/\//i.test(url)) url = 'https://' + url;
    navigating = true;
    if (frameTimer) clearTimeout(frameTimer);
    cover('正在加载 ' + url);
    message('正在导航…');
    try {
      await action('navigate', {url}, true);
      addressDirty = false;
      message('导航完成');
      await status();
    } catch (e) {
      addressDirty = true;
      message('导航失败：' + e.message);
    } finally {
      navigating = false;
      if (sid && active) frameTimer = setTimeout(frame, 0);
    }
  }
  $('manual-url').addEventListener('input', () => { addressDirty = true; });
  $('manual-url').addEventListener('keydown', e => {
    if (e.key === 'Enter' && sid) { e.preventDefault(); navigatePage($('manual-url').value); }
  });
  $('manual-go').addEventListener('click', () => navigatePage($('manual-url').value));
  $('manual-back').addEventListener('click', () => action('back'));
  $('manual-forward').addEventListener('click', () => action('forward'));
  function sizeRoot() {
    // Respect the actual position below CDIO's global navigation/header.
    // The frame expands into all remaining available viewport height.
    const top = Math.max(0, root.getBoundingClientRect().top);
    const target = Math.max(420, Math.floor(window.innerHeight - top - 12));
    root.style.height = target + 'px';
  }
  async function syncViewport() {
    if (!sid || navigating || !active) return;
    const box = $wrap.getBoundingClientRect();
    const width = Math.max(320, Math.min(2560, Math.round(box.width - 2)));
    const height = Math.max(240, Math.min(1800, Math.round(box.height - 2)));
    const dimensions = `${width}x${height}`;
    if (dimensions === viewportApplied) return;
    const token = sid;
    try {
      // Resize only the artificial/manual tab. Never resize another watch.
      await action('resize', {width, height}, true);
      if (token !== sid) return;
      viewportApplied = dimensions;
      viewportWidth = width;
      viewportHeight = height;
    } catch (e) {
      message('更新浏览器尺寸失败（仍可操作）：' + e.message);
    }
  }
  function scheduleLayout() {
    sizeRoot();
    if (layoutTimer) clearTimeout(layoutTimer);
    layoutTimer = setTimeout(syncViewport, 180);
  }
  window.addEventListener('resize', scheduleLayout);
  // Parent CDIO controls can change height without a window resize.
  if (typeof ResizeObserver !== 'undefined') {
    const observer = new ResizeObserver(() => {
      if (layoutTimer) clearTimeout(layoutTimer);
      layoutTimer = setTimeout(syncViewport, 180);
    });
    observer.observe($wrap);
  }
  sizeRoot();
  controls(false);
  inspectSession();
})();
