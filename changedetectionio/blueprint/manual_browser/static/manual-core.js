/* Shared session ownership, authenticated HTTP transport and ordered commands.
 * Do not disclose the token in links, logs, or the browser's persistent storage.
 */
(() => {
  'use strict';
  window.ManualBrowser = window.ManualBrowser || {};

  function createCore(config, hooks = {}) {
    const origin = (config.api || '/manual-browser/').replace(/\/$/, '') + '/api/';
    const csrf = config.csrf || '';
    let token = null;
    let generation = null;
    let epoch = 0;
    let busy = false;
    let commandTail = Promise.resolve();
    let inspectionId = 0;
    let transport = null;
    function setTransport(value) { transport = value; }

    function emit(name, ...args) { if (typeof hooks[name] === 'function') hooks[name](...args); }
    function state() { return {token, generation, epoch, busy}; }
    function active() { return Boolean(token); }
    function valid(ticket) { return token === ticket.token && epoch === ticket.epoch; }
    function snapshot() { return {token, epoch}; }
    function setBusy(value) { busy = value; emit('busy', value); }

    async function request(path, data) {
      const response = await fetch(origin + path, {
        method: data === undefined ? 'GET' : 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        headers: {
          'X-CSRFToken': csrf,
          ...(data === undefined ? {} : {'Content-Type': 'application/json'}),
        },
        ...(data === undefined ? {} : {body: JSON.stringify(data)}),
      });
      if (!response.ok) {
        let message = `HTTP ${response.status}`;
        try {
          const raw = await response.text();
          try { message = JSON.parse(raw).error || message; }
          catch (_) { message = raw.slice(0, 180) || message; }
        } catch (_) { /* preserve HTTP status */ }
        const err = new Error(message);
        err.status = response.status;
        throw err;
      }
      return response;
    }
    async function api(path, data) { return (await request(path, data)).json(); }
    function terminal(error) {
      return Boolean(error && ([400,401,403,404,409].includes(error.status) ||
        /浏览器实例已切换/.test(error.message)));
    }
    function disconnect(reason) {
      if (!token && !busy) return;
      if (transport) transport.close();
      token = null;
      generation = null;
      epoch++;
      ++inspectionId;
      commandTail = Promise.resolve();
      emit('disconnected', reason || '会话已断开');
    }
    function adopt(session, newGeneration) {
      if (transport) transport.close();
      token = session;
      generation = newGeneration;
      epoch++;
      commandTail = Promise.resolve();
      emit('connected', state());
    }
    function send(action, args = {}, required = false) {
      if (!token) return Promise.reject(new Error('浏览器尚未连接'));
      const ticket = snapshot();
      const next = commandTail.catch(() => {}).then(async () => {
        if (!valid(ticket)) throw new Error('会话已切换，已取消旧操作');
        const socketResult = transport && transport.send(action, args);
        return socketResult || api('action', {session: ticket.token, action, ...args});
      });
      // Continue processing future actions even after one command fails.
      commandTail = next.catch(() => {});
      if (!required) {
        return next.catch(error => {
          if (valid(ticket)) {
            if (terminal(error)) disconnect('操作会话已失效：' + error.message);
            else emit('message', '操作失败：' + error.message);
          }
        });
      }
      return next;
    }
    async function connect(url, watchUuid) {
      if (token || busy) return;
      setBusy(true);
      emit('message', '正在连接浏览器…');
      try {
        const data = await api('open', {url, watch_uuid: watchUuid});
        adopt(data.session, data.generation);
      } catch (error) {
        emit('message', '连接失败：' + error.message);
        await inspect();
      } finally { setBusy(false); }
    }
    async function resume(session) {
      if (busy) return;
      setBusy(true);
      try {
        const data = await api('resume', {session});
        adopt(data.session, data.generation);
      } catch (error) {
        emit('message', '恢复失败：' + error.message);
        await inspect();
      } finally { setBusy(false); }
    }
    async function end(path) {
      if (!token || busy) return;
      setBusy(true);
      const ticket = snapshot();
      try {
        const result = await api(path, {session:ticket.token});
        if (valid(ticket)) disconnect(result.recheck_queued ? '已关闭会话，已加入重新检查队列' : '已关闭人工会话');
        await inspect();
        emit('ended', {path, result});
      } catch (error) {
        if (valid(ticket)) emit('message', '关闭失败：' + error.message);
      } finally { setBusy(false); }
    }
    async function inspect() {
      const id = ++inspectionId;
      const previous = snapshot();
      try {
        const data = await api('current');
        // Ignore a stale lookup after any connection/token transition.
        if (id === inspectionId && previous.epoch === epoch && !active()) emit('inspected', data);
        return data;
      } catch (error) {
        if (id === inspectionId && !active()) emit('message', '查询会话失败：' + error.message);
        return null;
      }
    }
    async function switchSession(oldToken, destinationUrl, watchUuid) {
      if (busy || token) return;
      setBusy(true);
      try {
        await api('close', {session:oldToken});
        const data = await api('open', {url: destinationUrl, watch_uuid: watchUuid});
        adopt(data.session, data.generation);
      } catch (error) {
        emit('message', '切换失败：' + error.message);
        await inspect();
      } finally { setBusy(false); }
    }
    return {state, active, valid, snapshot, request, api, send, setTransport, terminal,
            disconnect, connect, resume, end, inspect, switchSession};
  }

  window.ManualBrowser.createCore = createCore;
})();
