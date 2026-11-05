/* WebSocket binary JPEG with independent HTTP screenshot/status fallback; not CDP. */
(() => {
  'use strict';
  window.ManualBrowser = window.ManualBrowser || {};
  function createStream(core, ui, hooks = {}) {
    let active = !document.hidden;
    let run = 0, frameTimer = null, statusTimer = null;
    let frameFailures = 0, statusFailures = 0;
    let shown = null, pending = null;
    let paused = false, frameRequest = null, refreshPending = false;
    let lastHumanAt = Date.now(), lastRefreshRequested = 0;
    let displayTimes = [];
    const FPS_WINDOW_MS = 5000;
    function updateFps(now = Date.now()) {
      displayTimes = displayTimes.filter(t => now - t <= FPS_WINDOW_MS);
      if (!displayTimes.length || now - displayTimes[displayTimes.length - 1] > 2500) {
        $safe('manual-fps', '0.0 FPS'); return;
      }
      // Count frames in a time window, rather than using a noisy single interval.
      const span = Math.min(FPS_WINDOW_MS, now - displayTimes[0]);
      const fps = span > 0 ? Math.max(0, (displayTimes.length - 1) * 1000 / span) : 0;
      $safe('manual-fps', `${fps.toFixed(1)} FPS`);
    }
    let transport = null;
    function setTransport(value) { transport = value; }
    const $safe = (id, value) => { const node = $(id); if (node) node.textContent = value; };
    const $ = id => document.getElementById(id);
    const img = $('manual-frame');
    const cover = $('manual-cover');
    const state = $('manual-state');

    function message(text) { state.textContent = text; }
    function coverFrame(text) {
      // Keep the empty-state icon and its styling when the frame is hidden.
      const label = typeof cover.querySelector === 'function' ? cover.querySelector('.manual-cover-label') : null;
      if (label) label.textContent = text;
      else cover.textContent = text; // lightweight DOM mocks and older markup
      cover.hidden = false;
      img.hidden = true;
    }
    function disposePending() {
      if (pending) { URL.revokeObjectURL(pending); pending = null; }
    }
    function stop(reason = '点击「连接浏览器」开始操作。') {
      run++;
      if (transport) transport.close();
      clearTimeout(frameTimer); clearTimeout(statusTimer);
      frameTimer = null; statusTimer = null;
      frameFailures = 0; statusFailures = 0;
      refreshPending = false; frameRequest = null;
      lastHumanAt = Date.now(); lastRefreshRequested = 0; displayTimes = [];
      $safe('manual-frame-latency', '—');
      for (const id of ['manual-screenshot-ms','manual-dispatch-ms','manual-display-ms','manual-frame-bytes','manual-ack-ms']) $safe(id, '—');
      $safe('manual-fps', '—');
      $safe('manual-action-latency', '—');
      img.onload = null; img.onerror = null;
      if (shown) { URL.revokeObjectURL(shown); shown = null; }
      disposePending();
      img.removeAttribute('src');
      $('manual-connection').textContent = '○ 未连接';
      $('manual-site-data').textContent = '';
      $('manual-remaining').textContent = '';
      $safe('manual-profile-status', 'Profile 状态待连接');
      $safe('manual-profile-lock', '—');
      $safe('manual-generation', '—');
      $safe('manual-cookies', '—');
      $safe('manual-local-storage', '—');
      $safe('manual-detail', '—');
      for (const id of ['manual-ua','manual-platform','manual-viewport','manual-dpr']) $safe(id, '—');
      const copyUa = $('manual-copy-ua');
      if (copyUa) copyUa.disabled = true;
      coverFrame(reason);
    }
    function defaultFrameDelay() {
      const idleMs = Date.now() - lastHumanAt;
      return idleMs < 3500 ? 180 : idleMs < 15000 ? 450 : 1000;
    }
    function nextFrame(ms = defaultFrameDelay()) {
      clearTimeout(frameTimer);
      if (core.active() && active && !paused && !(transport && (transport.isActive() || transport.isConnecting()))) frameTimer = setTimeout(frame, ms);
    }
    function nextStatus(ms = 2500) {
      clearTimeout(statusTimer);
      if (core.active() && active) statusTimer = setTimeout(status, ms);
    }
    async function frame() {
      if (!core.active() || !active || paused || frameRequest ||
          (transport && (transport.isActive() || transport.isConnecting()))) return;
      const ticket = core.snapshot();
      const cycle = run;
      const requestTag = {cycle};
      frameRequest = requestTag;
      const started = Date.now();
      let retryDelay = null;
      try {
        const response = await core.request('frame?session=' + encodeURIComponent(ticket.token));
        const blob = await response.blob();
        if (cycle !== run || !core.valid(ticket) || paused || !active || (transport && transport.isActive())) return;
        frameFailures = 0;
        $safe('manual-frame-latency', `${Date.now() - started} ms HTTP 往返`);
        $safe('manual-frame-bytes', `${Math.round(blob.size / 1024)} KiB`);
        $safe('manual-screenshot-ms', '—');
        $safe('manual-dispatch-ms', '—');
        $safe('manual-ack-ms', '—');
        displayBlob(blob, ticket, cycle);
      } catch (error) {
        if (cycle !== run || !core.valid(ticket)) return;
        if (core.terminal(error)) { core.disconnect('画面会话已失效：' + error.message); return; }
        frameFailures++;
        message(`画面暂时不可用，正在重试 (${frameFailures})：${error.message}`);
        retryDelay = Math.min(5000, 800 * frameFailures);
      } finally {
        if (frameRequest !== requestTag) return;
        frameRequest = null;
        if (cycle === run && core.valid(ticket) && !paused && active) {
          // One in-flight frame at most. A human action promotes the next frame.
          const delay = retryDelay === null ? (refreshPending ? 100 : defaultFrameDelay()) : retryDelay;
          refreshPending = false;
          nextFrame(delay);
        }
      }
    }
    function displayBlob(blob, ticket, cycle, acknowledged) {
      if (cycle !== run || !core.valid(ticket) || !active || paused) {
        if (acknowledged) acknowledged();
        return;
      }
      const decodeStarted = Date.now();
      const url = URL.createObjectURL(blob);
      disposePending();
      pending = url;
      img.onload = () => {
        if (cycle !== run || !core.valid(ticket) || pending !== url) {
          if (acknowledged) acknowledged();
          return;
        }
        const now = Date.now();
        displayTimes.push(now);
        updateFps(now);
        $safe('manual-display-ms', `${now - decodeStarted} ms`);
        if (shown) URL.revokeObjectURL(shown);
        shown = url; pending = null;
        img.hidden = false; cover.hidden = true;
        if (acknowledged) acknowledged();
      };
      img.onerror = () => {
        if (pending === url) { disposePending(); message('画面解码失败，将重试'); }
        if (acknowledged) acknowledged();
      };
      img.src = url;
    }
    function socketReady() {
      ++run;
      clearTimeout(frameTimer); frameTimer = null;
      frameRequest = null;
      if (core.active() && active) nextStatus(0);
    }
    function socketFallback() {
      if (!core.active()) return;
      ++run;
      frameRequest = null;
      message('WebSocket 不可用，已回退 HTTP 画面');
      if (active && !paused) nextFrame(0);
      if (active) nextStatus(0);
    }
    function socketFrame(data, ack) {
      if (!transport || !transport.isActive()) { ack(); return; }
      if (!data || typeof data.seq !== 'number' || !data.jpeg) { ack(); return; }
      $safe('manual-frame-latency', `${data.capture_ms ?? '—'} ms 服务端`);
      $safe('manual-screenshot-ms', typeof data.screenshot_ms === 'number' ? `${data.screenshot_ms} ms` : '—');
      $safe('manual-dispatch-ms', typeof data.dispatch_ms === 'number' ? `${data.dispatch_ms} ms` : '—');
      $safe('manual-frame-bytes', typeof data.bytes === 'number' ? `${Math.round(data.bytes / 1024)} KiB` : '—');
      $safe('manual-ack-ms', typeof data.previous_ack_ms === 'number' ? `${data.previous_ack_ms} ms` : '—');
      const blob = new Blob([data.jpeg], {type:'image/jpeg'});
      displayBlob(blob, core.snapshot(), run, ack);
    }
    function interaction() {
      lastHumanAt = Date.now();
      if (transport) transport.interaction();
    }
    function requestRefresh() {
      interaction();
      if (!core.active() || !active || paused) return;
      // Coalesce drag/wheel/key bursts; never start a concurrent HTTP frame request.
      const now = Date.now();
      if (now - lastRefreshRequested < 110) {
        refreshPending = true;
        return;
      }
      lastRefreshRequested = now;
      if (frameRequest) refreshPending = true;
      else nextFrame(100);
    }
    function actionCompleted(elapsed) {
      if (typeof elapsed === 'number' && Number.isFinite(elapsed)) {
        $safe('manual-action-latency', `${Math.max(0, Math.round(elapsed))} ms`);
      }
      if (!(transport && transport.isActive())) requestRefresh();
    }
    async function status() {
      if (!core.active() || !active) return;
      updateFps();
      const ticket = core.snapshot(), cycle = run;
      try {
        const data = await core.api('status?session=' + encodeURIComponent(ticket.token));
        if (cycle !== run || !core.valid(ticket)) return;
        if (data.generation !== core.state().generation) {
          core.disconnect('浏览器实例已切换'); return;
        }
        statusFailures = 0;
        $('manual-connection').textContent = data.challenge ? `● 验证页面：${data.challenge}` : '● 已连接';
        $('manual-site-data').textContent = `Cookie：${data.cookie_count} | LocalStorage：${data.local_storage_keys ?? '未知'}`;
        $safe('manual-profile-status', data.profile_lock_held ? 'Profile 已加载' : 'Profile 状态异常');
        $safe('manual-profile-lock', data.profile_lock_held ? '已持有' : '未持有');
        $safe('manual-generation', String(data.generation ?? '—'));
        $safe('manual-cookies', String(data.cookie_count ?? '—'));
        $safe('manual-local-storage', String(data.local_storage_keys ?? '未知'));
        $('manual-remaining').textContent = `空闲剩余 ${Math.floor(data.seconds_remaining / 60)}:${String(data.seconds_remaining % 60).padStart(2, '0')}`;
        $safe('manual-detail', data.url || '—');
        $safe('manual-ua', data.user_agent || '暂不可用');
        $safe('manual-platform', data.platform || '暂不可用');
        $safe('manual-viewport', data.width && data.height ? `${data.width} × ${data.height}` : '暂不可用');
        $safe('manual-dpr', Number.isFinite(data.device_pixel_ratio) ? String(data.device_pixel_ratio) : '暂不可用');
        const copyUa = $('manual-copy-ua');
        if (copyUa) copyUa.disabled = !data.user_agent;
        if (hooks.status) hooks.status(data);
        if (!paused) message(data.challenge ? '页面仍要求验证，可继续人工操作' : '浏览器已连接');
      } catch (error) {
        if (cycle !== run || !core.valid(ticket)) return;
        if (core.terminal(error)) { core.disconnect('会话已失效：' + error.message); return; }
        statusFailures++;
        message(`状态暂时不可用，正在重试 (${statusFailures})：${error.message}`);
        nextStatus(Math.min(7000, 1500 * statusFailures));
        return;
      }
      nextStatus();
    }
    function start() {
      stop('正在获取实时画面…');
      if (!core.active()) return;
      active = !document.hidden;
      paused = false;
      if (active) { frame(); status(); }
      if (transport) transport.start();
    }
    function suspend(text) {
      if (transport) transport.view(false);
      paused = true;
      clearTimeout(frameTimer);
      coverFrame(text);
    }
    function resumeFrames() {
      paused = false;
      if (core.active() && active) {
        if (transport && transport.isActive()) transport.view(true);
        else nextFrame(0);
      }
    }
    function visibilityChanged() {
      active = !document.hidden;
      if (!active) {
        // Retire in-flight frame/status responses from the now-hidden tab.
        run++; frameRequest = null; refreshPending = false;
        clearTimeout(frameTimer); clearTimeout(statusTimer);
        if (transport) transport.view(false);
      } else if (core.active()) {
        if (transport && transport.isActive()) transport.view(true);
        else nextFrame(0);
        nextStatus(0);
      }
    }
    function shutdown() {
      stop();
      active = false;
    }
    return {start,stop,setTransport,socketReady,socketFallback,socketFrame,suspend,resumeFrames,visibilityChanged,shutdown,coverFrame,interaction,requestRefresh,actionCompleted};
  }
  window.ManualBrowser.createStream = createStream;
})();
