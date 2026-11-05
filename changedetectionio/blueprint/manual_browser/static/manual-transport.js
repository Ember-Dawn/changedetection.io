/* Socket.IO transport; independent Engine.IO connections prevent JPEG frames
 * from queueing ahead of latency-sensitive input. HTTP remains a safe fallback.
 */
(() => {
  'use strict';
  window.ManualBrowser = window.ManualBrowser || {};
  function createTransport(core, config, hooks = {}) {
    let input = null, frames = null, epoch = 0, seq = 0, active = false;
    let inputReady = false, frameReady = false, connecting = false;
    let timeout = null;
    const enabled = () => Boolean(window.io && typeof window.io === 'function');
    function notify() { if (hooks.state) hooks.state(active ? 'WebSocket' : 'HTTP'); }
    function close() {
      ++epoch; active = false; inputReady = false; frameReady = false; connecting = false;
      clearTimeout(timeout); timeout = null;
      if (input) { input.removeAllListeners(); input.disconnect(); input = null; }
      if (frames) { frames.removeAllListeners(); frames.disconnect(); frames = null; }
      notify();
    }
    function fail() {
      if (!active && !connecting) return;
      close();
      if (hooks.fallback) hooks.fallback();
    }
    function start() {
      close();
      if (!core.active() || !enabled() || config.transport === 'http') return;
      const ticket = core.snapshot(), cycle = epoch;
      connecting = true;
      const auth = {csrf: config.csrf, session: ticket.token, generation:core.state().generation};
      const frameAuth = {...auth, frame_engine:config.frameEngine === 'cdp' ? 'cdp' : 'jpeg'};
      const options = {path: config.socketioPath || '/socket.io',
        transports:['websocket'], reconnection:false, forceNew:true, auth, timeout:3500};
      try {
        input = window.io('/manual-input', options);
        frames = window.io('/manual-frames', {...options, auth:frameAuth});
      } catch (_) { fail(); return; }
      const good = () => {
        if (cycle !== epoch || !core.valid(ticket)) return;
        if (inputReady && frameReady) {
          connecting = false; active = true;
          clearTimeout(timeout);
          notify();
          if (hooks.ready) hooks.ready();
        }
      };
      input.on('connect', () => {inputReady = true; good();});
      frames.on('connect', () => {frameReady = true; good();});
      for (const socket of [input, frames]) {
        socket.on('disconnect', fail);
        socket.on('connect_error', fail);
      }
      frames.on('frame', data => {
        if (!active || cycle !== epoch || !core.valid(ticket)) return;
        if (hooks.frame) hooks.frame(data, () => {
          if (active && frames && cycle === epoch) frames.emit('frame_ack', {seq:data.seq});
        });
      });
      frames.on('engine_fallback', data => {
        if (cycle === epoch && hooks.engineFallback) hooks.engineFallback(data && data.engine);
      });
      frames.on('stream_end', fail);
      timeout = setTimeout(() => {if (!active) fail();}, 4500);
    }
    function send(action, args={}) {
      if (!active || !input) return null;
      const ticket = core.snapshot(), cycle = epoch;
      return new Promise((resolve,reject) => {
        let settled = false;
        const finish = (error, value) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          if (error) reject(error); else resolve(value);
        };
        const timer = setTimeout(() => {fail(); finish(new Error('WebSocket input timed out'));}, 42000);
        input.emit('action', {action, ...args, seq:++seq}, response => {
          if (cycle !== epoch || !core.valid(ticket)) {
            finish(new Error('会话已切换，已取消旧操作')); return;
          }
          if (!response || !response.ok) {
            const error = new Error(response && response.error || 'WebSocket input failed');
            if (response && response.terminal) error.status = 409;
            finish(error); return;
          }
          finish(null, response.result);
        });
      });
    }
    function view(activeView) {if (active && frames) frames.emit('view', {active:activeView});}
    function interaction() {if (active && frames) frames.emit('interaction', {});}
    return {start,close,send,view,interaction,isActive:()=>active,isConnecting:()=>connecting};
  }
  window.ManualBrowser.createTransport = createTransport;
})();
