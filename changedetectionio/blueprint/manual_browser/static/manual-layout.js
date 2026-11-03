/* Full-height canvas and viewport resize, isolated to the manual Page. */
(() => {
  'use strict';
  window.ManualBrowser = window.ManualBrowser || {};
  function createLayout(core, hooks = {}) {
    const root = document.getElementById('manual-browser-root');
    const wrap = document.getElementById('manual-frame-wrap');
    let timer = null, observer = null, generation = 0, applied = '';
    let pending = false, resizeAgain = false;
    let width = 1366, height = 768;
    function viewport() { return {width, height}; }
    function measureRoot() {
      // A flex child may occupy all height below changedetection's top navigation.
      const top = Math.max(0, root.getBoundingClientRect().top);
      const space = Math.max(420, Math.floor(window.innerHeight - top - 12));
      root.style.height = `${space}px`;
    }
    function desiredSize() {
      const bounds = wrap.getBoundingClientRect();
      const w = Math.min(2560, Math.max(320, Math.round(bounds.width - 2)));
      const h = Math.min(1800, Math.max(240, Math.round(bounds.height - 2)));
      return {width:w, height:h, key:`${w}x${h}`};
    }
    async function sync() {
      if (!core.active()) return;
      if (pending) { resizeAgain = true; return; }
      const ticket = core.snapshot();
      const cycle = generation;
      const size = desiredSize();
      if (size.key === applied) return;
      pending = true;
      try {
        await core.send('resize', {width:size.width, height:size.height}, true);
        if (cycle !== generation || !core.valid(ticket)) return;
        applied = size.key;
        width = size.width; height = size.height;
        if (hooks.resized) hooks.resized(viewport());
      } catch (error) {
        if (core.valid(ticket) && hooks.error) hooks.error('调整浏览器尺寸失败：' + error.message);
      } finally {
        pending = false;
        if (resizeAgain) { resizeAgain = false; schedule(); }
      }
    }
    function schedule() {
      measureRoot();
      clearTimeout(timer);
      timer = setTimeout(sync, 180);
    }
    function start() { generation++; applied = ''; measureRoot(); return sync(); }
    function reset() { generation++; clearTimeout(timer); applied = ''; resizeAgain = false; }
    function init() {
      measureRoot();
      window.addEventListener('resize', schedule);
      if (typeof ResizeObserver !== 'undefined') {
        observer = new ResizeObserver(schedule);
        observer.observe(wrap);
      }
    }
    function shutdown() {
      reset();
      window.removeEventListener('resize', schedule);
      if (observer) { observer.disconnect(); observer = null; }
    }
    return {viewport,init,start,schedule,reset,shutdown};
  }
  window.ManualBrowser.createLayout = createLayout;
})();
