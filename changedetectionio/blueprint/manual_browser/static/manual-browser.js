/* Manual browser entrypoint. All requests stay on same-origin authenticated APIs. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const ns = window.ManualBrowser;
  const config = window.manualBrowserConfig || {};
  const initialUrl = $('manual-url').value.trim();
  const watchUuid = $('manual-watch-uuid').value.trim();
  const transportMode = $('manual-transport-mode');
  try {config.transport = localStorage.getItem('changedetection.manual-transport') === 'http' ? 'http' : 'auto';}
  catch (_) {config.transport = 'auto';}
  if (transportMode) {
    transportMode.value = config.transport;
    // CDSelect is initialized after the scripts load; sync handles later changes.
    if (window.CDSelect) window.CDSelect.sync(transportMode);
  }
  const frameMode = $('manual-frame-engine');
  try {config.frameEngine = localStorage.getItem('changedetection.manual-frame-engine') === 'cdp' ? 'cdp' : 'jpeg';}
  catch (_) {config.frameEngine = 'jpeg';}
  if (frameMode) {frameMode.value = config.frameEngine; if (window.CDSelect) window.CDSelect.sync(frameMode);}
  let existing = null;
  let stream, layout, input, transport;

  function message(text) {
    const node = $('manual-state');
    node.textContent = text;
    // The connection badge already conveys the ordinary connected state.
    node.hidden = !text || text === '浏览器已连接' || text === '人工操作已连接' || text === '未连接';
  }
  function finishVisibility() {
    const node = $('manual-finish');
    // Entry context AND actual session association must match. A general
    // Browsers tab resuming an old Watch session never gains a finish button.
    node.hidden = !(watchUuid && core.active() && core.state().watch_uuid === watchUuid);
  }
  function controls(connected, busy = false) {
    for (const id of ['manual-refresh', 'manual-finish', 'manual-close', 'manual-type',
                      'manual-enter','manual-backspace','manual-go','manual-back','manual-forward']) {
      $(id).disabled = !connected || busy;
    }
    $('manual-open').disabled = connected || busy || $('manual-existing').hidden === false;
    finishVisibility();
  }
  function showExisting(data) {
    existing = data && data.active ? data : null;
    const banner = $('manual-existing');
    banner.hidden = !data || (!data.active && !data.opening);
    $('manual-resume').hidden = !data || !data.active || !data.owned;
    $('manual-switch').hidden = !data || !data.active || !data.owned;
    if (data && data.active) {
      $('manual-existing-title').textContent = data.owned ? '已有你的人工操作会话' : '人工浏览器正由其他登录用户操作';
      $('manual-existing-description').textContent =
        `${data.owned ? data.url : '会话地址仅对所有者可见'} · 空闲剩余约 ${Math.ceil(data.seconds_remaining/60)} 分钟`;
    } else if (data && data.opening) {
      $('manual-existing-title').textContent = '浏览器会话正在创建或清理';
      $('manual-existing-description').textContent = '请稍后点击「刷新状态」。';
    }
    controls(core.active(), core.state().busy);
  }
  const core = ns.createCore(config, {
    message,
    busy(value) { controls(core.active(), value); },
    inspected:showExisting,
    connected() {
      existing = null;
      $('manual-existing').hidden = true;
      controls(true);
      message('人工操作已连接');
      $('manual-connection').textContent = '● 已连接';
      finishVisibility();
      input.reset();
      // Resize first so that screenshots and click coordinates refer to the
      // same viewport. Failure to resize is non-terminal.
      const ticket = core.snapshot();
      Promise.resolve(layout.start()).finally(() => {
        if (core.valid(ticket)) stream.start();
      });
    },
    disconnected(reason) {
      stream.stop('会话已结束，可重新连接。');
      layout.reset();
      input.reset();
      showExisting(null);
      controls(false);
      message(reason);
      core.inspect();
    },

  });
  stream = ns.createStream(core, {}, {status(data) { input.applyStatus(data); }});
  transport = ns.createTransport(core, config, {
    ready() { stream.socketReady(); },
    fallback() { stream.socketFallback(); },
    frame(data, ack) { stream.socketFrame(data, ack); },
    engineFallback() {stream.engineFallback();},
    state(mode) {const node = $('manual-transport'); if (node) node.textContent = mode;},
  });
  core.setTransport(transport);
  stream.setTransport(transport);
  if (transportMode) transportMode.addEventListener('change', event => {
    config.transport = event.target.value === 'http' ? 'http' : 'auto';
    try {localStorage.setItem('changedetection.manual-transport', config.transport);} catch (_) {}
    if (!core.active()) return;
    message(config.transport === 'http' ? '正在切换至 HTTP 兼容模式…' : '正在连接 WebSocket…');
    if (config.transport === 'http') {transport.close(); stream.socketFallback();}
    else transport.start();
  });
  if (frameMode) frameMode.addEventListener('change', event => {
    config.frameEngine = event.target.value === 'cdp' ? 'cdp' : 'jpeg';
    try {localStorage.setItem('changedetection.manual-frame-engine', config.frameEngine);} catch (_) {}
    if (!core.active()) return;
    message('正在切换画面引擎…');
    const engineStatus = $('manual-frame-engine-status');
    if (engineStatus) engineStatus.textContent = '正在切换…';
    if (config.transport === 'http' && config.frameEngine === 'cdp') {
      config.transport = 'auto';
      if (transportMode) {transportMode.value = 'auto'; if (window.CDSelect) window.CDSelect.sync(transportMode);}
      try {localStorage.setItem('changedetection.manual-transport', 'auto');} catch (_) {}
    }
    if (config.transport === 'http') return;
    transport.close();
    stream.socketFallback();
    // The server owns CDP cleanup. Allow the old producer to release its
    // CDPSession before opening the replacement viewer connection.
    setTimeout(() => {if (core.active() && config.transport !== 'http') transport.start();}, 250);
  });
  const copyUa = $('manual-copy-ua');
  if (copyUa) copyUa.addEventListener('click', async () => {
    const ua = $('manual-ua').textContent;
    if (!ua || ua === '—' || ua === '暂不可用') return;
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(ua);
      copyUa.textContent = '已复制';
      setTimeout(() => { copyUa.textContent = '复制 UA'; }, 1500);
    } catch (_) { message('复制失败，请手动选中 UA 后复制'); }
  });
  layout = ns.createLayout(core, {
    error(text) { message(text); stream.resumeFrames(); },
    changing() { if (core.active()) stream.suspend('正在调整浏览器画面…'); },
    resized() { if (core.active()) stream.resumeFrames(); },
    modeChanged(mode) { $('manual-viewport-mode').value = mode; if (window.CDSelect) window.CDSelect.sync($('manual-viewport-mode')); },
  });
  $('manual-viewport-mode').value = layout.currentMode();
  $('manual-viewport-mode').addEventListener('change', event => layout.setMode(event.target.value));
  input = ns.createInput(core, stream, layout, {message});

  $('manual-open').addEventListener('click', () => {
    if (core.active() || core.state().busy || existing) return;
    const url = $('manual-url').value.trim();
    if (!url && !watchUuid) {
      message('请输入网址，再连接浏览器。');
      $('manual-url').focus();
      return;
    }
    core.connect(url, watchUuid);
  });
  $('manual-close').addEventListener('click', () => core.end('close'));
  $('manual-finish').addEventListener('click', () => {
    if (!watchUuid || core.state().watch_uuid !== watchUuid) return;
    core.end('finish');
  });
  $('manual-check').addEventListener('click', () => core.inspect());
  $('manual-resume').addEventListener('click', () => {
    if (existing && existing.owned) core.resume(existing.session);
  });
  $('manual-switch').addEventListener('click', () => {
    if (!existing || !existing.owned || core.state().busy) return;
    const destination = $('manual-url').value.trim() || initialUrl;
    if (!destination && !watchUuid) {
      message('请先输入新网站网址，再切换旧会话。');
      return;
    }
    if (!window.confirm('关闭已有会话并打开当前网站？旧网页中未保存的输入可能丢失。')) return;
    core.switchSession(existing.session, destination, watchUuid);
  });
  document.addEventListener('visibilitychange', () => stream.visibilityChanged());
  window.addEventListener('pagehide', () => { stream.shutdown(); layout.shutdown(); });
  input.init();
  layout.init();
  controls(false);
  // Only Watch-origin links opt in to connecting automatically. General
  // Browsers entry stays manual, and an existing session is never stolen.
  const query = (window.location && window.location.search) || '';
  const autoConnect = /(?:^|[?&])autoconnect=1(?:&|$)/.test(query);
  if (autoConnect && watchUuid) {
    core.inspect().then(data => {
      if (!data || data.active || data.opening || core.active() || core.state().busy) return;
      core.connect($('manual-url').value.trim(), watchUuid);
    });
  } else {
    core.inspect();
  }
})();
