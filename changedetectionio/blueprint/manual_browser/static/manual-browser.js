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
  let existing = null;
  let stream, layout, input, transport;

  function message(text) { $('manual-state').textContent = text; }
  function controls(connected, busy = false) {
    for (const id of ['manual-refresh', 'manual-finish', 'manual-close', 'manual-type',
                      'manual-enter','manual-backspace','manual-go','manual-back','manual-forward']) {
      $(id).disabled = !connected || busy;
    }
    $('manual-open').disabled = connected || busy || $('manual-existing').hidden === false;
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
    ended({path}) {
      if (path === 'finish' && !watchUuid) {
        $('manual-detail').textContent = '请返回新增监控页，再点击「前往」刷新预览。';
      }
    },
  });
  stream = ns.createStream(core, {}, {status(data) { input.applyStatus(data); }});
  transport = ns.createTransport(core, config, {
    ready() { stream.socketReady(); },
    fallback() { stream.socketFallback(); },
    frame(data, ack) { stream.socketFrame(data, ack); },
    state(mode) {const node = $('manual-transport'); if (node) node.textContent = mode;},
  });
  core.setTransport(transport);
  stream.setTransport(transport);
  if (transportMode) transportMode.addEventListener('change', event => {
    config.transport = event.target.value === 'http' ? 'http' : 'auto';
    try {localStorage.setItem('changedetection.manual-transport', config.transport);} catch (_) {}
    if (!core.active()) return;
    if (config.transport === 'http') {transport.close(); stream.socketFallback();}
    else transport.start();
  });
  const copyUrl = $('manual-copy-url');
  const currentUrl = $('manual-detail');
  if (copyUrl && currentUrl) {
    copyUrl.addEventListener('click', async () => {
      const url = currentUrl.textContent.trim();
      if (!url || url === '—') return;
      try {
        if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('Clipboard unavailable');
        await navigator.clipboard.writeText(url);
        copyUrl.textContent = '已复制';
        setTimeout(() => {copyUrl.textContent = '复制网址';}, 1500);
      } catch (_) {message('复制失败，请手动选择网址后复制');}
    });
  }
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
  $('manual-finish').addEventListener('click', () => core.end('finish'));
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
  core.inspect();
})();
