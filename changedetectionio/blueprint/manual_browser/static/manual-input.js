/* Playwright input and address-bar actions. Coordinates are based on shown image. */
(() => {
  'use strict';
  window.ManualBrowser = window.ManualBrowser || {};
  function createInput(core, stream, layout, hooks = {}) {
    const $ = id => document.getElementById(id);
    const wrap = $('manual-frame-wrap');
    const img = $('manual-frame');
    let dragging = false, pendingMove = null, lastPointer = null, moving = null, navigating = false, releasing = false;
    let dirty = false;
    let inFlight = null;
    function message(text) { if (hooks.message) hooks.message(text); }
    // Refresh after the remote action completes, rather than only waiting for
    // the passive screenshot timer. Stream keeps requests single-flight.
    function sendAndRefresh(action, args = {}) {
      if (typeof stream.interaction === 'function') stream.interaction();
      const started = Date.now();
      return Promise.resolve(core.send(action, args)).then(result => {
        if (typeof stream.actionCompleted === 'function') stream.actionCompleted(Date.now() - started);
        return result;
      });
    }
    function reset() { dragging = false; pendingMove = null; lastPointer = null; navigating = false; releasing = false; dirty = false; }
    function point(event) {
      const rect = img.getBoundingClientRect();
      if (img.hidden || !rect.width || !rect.height ||
          event.clientX < rect.left || event.clientX > rect.right ||
          event.clientY < rect.top || event.clientY > rect.bottom) return null;
      const {width, height} = layout.viewport();
      return {x:Math.max(0,Math.min(width,(event.clientX - rect.left) * width / rect.width)),
              y:Math.max(0,Math.min(height,(event.clientY - rect.top) * height / rect.height))};
    }
    function flushMoves() {
      if (moving) return moving;
      moving = (async () => {
        while (core.active() && pendingMove) {
          const latest = pendingMove;
          pendingMove = null;
          await sendAndRefresh('move', latest);
        }
      })().finally(() => { moving = null; });
      return moving;
    }
    async function release(event) {
      if (!dragging || releasing) return;
      releasing = true;
      const p = point(event) || pendingMove || lastPointer;
      if (p) pendingMove = p;
      dragging = false;
      try {
        await flushMoves();
        if (core.active() && p) await sendAndRefresh('up', p);
      } finally {
        pendingMove = null; lastPointer = null; releasing = false;
        if (wrap.hasPointerCapture && wrap.hasPointerCapture(event.pointerId))
          wrap.releasePointerCapture(event.pointerId);
      }
    }
    async function navigate(action, args = {}) {
      if (!core.active() || navigating) return;
      navigating = true;
      stream.suspend(action === 'navigate' ? '正在导航…' : '页面加载中…');
      const ticket = core.snapshot();
      const started = Date.now();
      try {
        await core.send(action, args, true);
        if (core.valid(ticket)) {
          if (action === 'navigate') dirty = false;
          message(action === 'navigate' ? '导航完成' : '页面已更新');
          if (typeof stream.actionCompleted === 'function') stream.actionCompleted(Date.now() - started);
        }
      } catch (error) {
        if (core.valid(ticket)) message('页面操作失败：' + error.message);
      } finally {
        navigating = false;
        stream.resumeFrames();
      }
    }
    function forwardUrl() {
      const raw = $('manual-url').value.trim();
      if (!raw) { message('请输入网址'); return; }
      const url = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
      navigate('navigate', {url});
    }
    function applyStatus(data) {
      if (!dirty && document.activeElement !== $('manual-url')) $('manual-url').value = data.url;
    }
    function init() {
      wrap.addEventListener('pointerdown', event => {
        if (!core.active() || releasing || event.button !== 0 || event.target !== img) return;
        const p = point(event); if (!p) return;
        event.preventDefault(); wrap.focus(); dragging = true; lastPointer = p;
        wrap.setPointerCapture(event.pointerId);
        sendAndRefresh('down', p);
      });
      wrap.addEventListener('pointermove', event => {
        if (!core.active() || releasing) return;
        const p = point(event);
        if (p) { pendingMove = p; lastPointer = p; flushMoves(); }
      });
      wrap.addEventListener('pointerup', release);
      wrap.addEventListener('pointercancel', release);
      wrap.addEventListener('lostpointercapture', event => {
        if (dragging && !releasing) release(event);
      });
      wrap.addEventListener('wheel', event => {
        if (!core.active()) return;
        const p = point(event);
        if (!p) return;
        event.preventDefault();
        sendAndRefresh('scroll', {...p, dx:event.deltaX, dy:event.deltaY});
      }, {passive:false});
      wrap.addEventListener('keydown', event => {
        if (!core.active() || event.ctrlKey || event.altKey || event.metaKey) return;
        const allowed = ['Enter','Tab','Escape','Backspace','Delete',' ','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End','PageUp','PageDown'];
        if (allowed.includes(event.key) || event.key.length === 1) {
          event.preventDefault();
          sendAndRefresh('key', {key:event.key === ' ' ? 'Space' : event.key});
        }
      });
      $('manual-url').addEventListener('input', () => { dirty = true; });
      $('manual-url').addEventListener('keydown', event => {
        if (event.key === 'Enter' && core.active()) { event.preventDefault(); forwardUrl(); }
      });
      $('manual-go').addEventListener('click', forwardUrl);
      $('manual-refresh').addEventListener('click', () => navigate('refresh'));
      $('manual-back').addEventListener('click', () => navigate('back'));
      $('manual-forward').addEventListener('click', () => navigate('forward'));
      $('manual-enter').addEventListener('click', () => sendAndRefresh('key', {key:'Enter'}));
      $('manual-backspace').addEventListener('click', () => sendAndRefresh('key', {key:'Backspace'}));
      $('manual-type').addEventListener('click', async () => {
        const input = $('manual-text');
        const text = input.value;
        if (!text || !core.active()) return;
        const ticket = core.snapshot();
        await sendAndRefresh('text', {text});
        if (core.valid(ticket) && input.value === text) input.value = '';
      });
    }
    return {init,reset,applyStatus,point};
  }
  window.ManualBrowser.createInput = createInput;
})();
