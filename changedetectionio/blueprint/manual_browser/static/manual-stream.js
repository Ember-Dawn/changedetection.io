/* JPEG polling and status polling are independently retryable. They are not a CDP stream. */
(() => {
  'use strict';
  window.ManualBrowser = window.ManualBrowser || {};
  function createStream(core, ui, hooks = {}) {
    let active = !document.hidden;
    let run = 0, frameTimer = null, statusTimer = null;
    let frameFailures = 0, statusFailures = 0;
    let shown = null, pending = null;
    let paused = false;
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
      clearTimeout(frameTimer); clearTimeout(statusTimer);
      frameTimer = null; statusTimer = null;
      frameFailures = 0; statusFailures = 0;
      img.onload = null; img.onerror = null;
      if (shown) { URL.revokeObjectURL(shown); shown = null; }
      disposePending();
      img.removeAttribute('src');
      $('manual-connection').textContent = '○ 未连接';
      $('manual-site-data').textContent = '';
      $('manual-remaining').textContent = '';
      coverFrame(reason);
    }
    function nextFrame(ms = 400) {
      clearTimeout(frameTimer);
      if (core.active() && active && !paused) frameTimer = setTimeout(frame, ms);
    }
    function nextStatus(ms = 2500) {
      clearTimeout(statusTimer);
      if (core.active() && active) statusTimer = setTimeout(status, ms);
    }
    async function frame() {
      if (!core.active() || !active || paused) return;
      const ticket = core.snapshot();
      const cycle = run;
      try {
        const response = await core.request('frame?session=' + encodeURIComponent(ticket.token));
        const blob = await response.blob();
        if (cycle !== run || !core.valid(ticket) || paused) return;
        frameFailures = 0;
        const url = URL.createObjectURL(blob);
        disposePending();
        pending = url;
        img.onload = () => {
          if (cycle !== run || !core.valid(ticket) || pending !== url) return;
          if (shown) URL.revokeObjectURL(shown);
          shown = url;
          pending = null;
          img.hidden = false;
          cover.hidden = true;
        };
        img.onerror = () => {
          if (pending === url) { disposePending(); message('画面解码失败，将重试'); }
        };
        img.src = url;
      } catch (error) {
        if (cycle !== run || !core.valid(ticket)) return;
        if (core.terminal(error)) { core.disconnect('画面会话已失效：' + error.message); return; }
        frameFailures++;
        message(`画面暂时不可用，正在重试 (${frameFailures})：${error.message}`);
        nextFrame(Math.min(5000, 800 * frameFailures));
        return;
      }
      nextFrame();
    }
    async function status() {
      if (!core.active() || !active) return;
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
        $('manual-remaining').textContent = `空闲剩余 ${Math.floor(data.seconds_remaining / 60)}:${String(data.seconds_remaining % 60).padStart(2, '0')}`;
        $('manual-detail').textContent = `实际网址：${data.url} | Profile 锁：${data.profile_lock_held ? '持有' : '未持有'} | 浏览器代次：${data.generation}`;
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
    }
    function suspend(text) {
      paused = true;
      clearTimeout(frameTimer);
      coverFrame(text);
    }
    function resumeFrames() {
      paused = false;
      if (core.active() && active) nextFrame(0);
    }
    function visibilityChanged() {
      active = !document.hidden;
      if (!active) {
        // Retire in-flight frame/status responses from the now-hidden tab.
        run++;
        clearTimeout(frameTimer); clearTimeout(statusTimer);
      } else if (core.active()) { nextFrame(0); nextStatus(0); }
    }
    function shutdown() {
      stop();
      active = false;
    }
    return {start,stop,suspend,resumeFrames,visibilityChanged,shutdown,coverFrame};
  }
  window.ManualBrowser.createStream = createStream;
})();
