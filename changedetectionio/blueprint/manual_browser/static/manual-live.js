/* Live desktop state/actions are independent of the screenshot manual session. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const start = $('manual-live-start'), stop = $('manual-live-stop');
  if (!start || !stop) return;
  const status = $('manual-live-status'), message = $('manual-live-message');
  const frame = $('manual-live-frame'), iframe = $('manual-live-iframe');
  const popup = $('manual-live-popup'), shell = $('manual-capture-panel');
  const livePanel = $('manual-live-panel'), placeholder = $('manual-live-placeholder');
  const captureTab = $('manual-mode-capture'), liveTab = $('manual-mode-live');
  const confirmation = $('manual-live-confirm');
  const confirmAccept = $('manual-live-confirm-accept');
  const confirmCancel = $('manual-live-confirm-cancel');
  const csrf = $('manual-csrf').value;
  const root = window.manualBrowserConfig.api.replace(/\/$/, '');
  let busy = false, lastPhase = null, selectedMode = 'capture';
  function setMode(mode) {
    selectedMode = mode;
    captureTab.setAttribute('aria-selected', String(mode === 'capture'));
    liveTab.setAttribute('aria-selected', String(mode === 'live'));
    captureTab.tabIndex = mode === 'capture' ? 0 : -1;
    liveTab.tabIndex = mode === 'live' ? 0 : -1;
    livePanel.hidden = mode !== 'live';
    shell.hidden = mode !== 'capture';
    start.hidden = mode !== 'live' || start.dataset.available !== 'true';
    stop.hidden = mode !== 'live' || stop.dataset.available !== 'true';
    popup.hidden = mode !== 'live' || popup.dataset.available !== 'true';
  }
  captureTab.addEventListener('click', () => { if (!captureTab.disabled) setMode('capture'); });
  liveTab.addEventListener('click', () => setMode('live'));
  for (const tab of [captureTab, liveTab]) {
    tab.addEventListener('keydown', event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const next = tab === captureTab ? liveTab : captureTab;
      if (!next.disabled) { next.focus(); setMode(next === liveTab ? 'live' : 'capture'); }
    });
  }
  const showError = text => {message.textContent=text || '';message.hidden=!text;};
  async function api(path, method='GET') {
    const res = await fetch(root+'/api/live/'+path, {method, credentials:'same-origin',
      headers:{'X-CSRFToken':csrf,'Content-Type':'application/json','Accept':'application/json'},
      ...(method==='POST'?{body:'{}'}:{})});
    const data=await res.json();
    if (!res.ok) throw new Error(data.error || '实时浏览器请求失败');
    return data;
  }
  function render(s) {
    const active = s.phase==='active', idle=s.phase==='idle';
    const ours=s.owned;
    status.textContent=({idle:'Headless · 正常监控',starting:'正在启动…',active:'Headed · 监控已暂停',stopping:'正在恢复…',error:'恢复失败 · 监控保持暂停'})[s.phase] || s.phase;
    start.dataset.available = String(idle);
    stop.dataset.available = String(ours && (active || s.phase === 'error'));
    popup.dataset.available = String(ours && active);
    start.disabled=busy;stop.disabled=busy;
    captureTab.disabled = !idle;
    if (!idle && selectedMode !== 'live') selectedMode = 'live';
    if (idle && lastPhase && lastPhase !== 'idle') selectedMode = 'capture';
    setMode(selectedMode);
    frame.hidden=!(ours&&active);
    placeholder.hidden=!!(ours&&active);
    if(active && !iframe.getAttribute('src')) iframe.src=popup.href;
    if(!active && iframe.getAttribute('src')) iframe.removeAttribute('src');
    if(s.error) showError(s.error);
    if (lastPhase!==s.phase && s.phase==='idle' && !s.error) showError('');
    lastPhase=s.phase;
  }
  async function refresh() {try {render(await api('status'));}catch(e){showError(e.message);}}
  function askToStart() {
    return new Promise(resolve => {
      if (!confirmation || !confirmAccept || !confirmCancel) {
        resolve(false);
        return;
      }
      let settled = false;
      function finish(accepted) {
        if (settled) return;
        settled = true;
        confirmation.removeEventListener('close', onClose);
        confirmAccept.removeEventListener('click', onAccept);
        confirmCancel.removeEventListener('click', onCancel);
        if (confirmation.open) confirmation.close();
        resolve(accepted);
      }
      function onClose() { finish(false); }
      function onAccept() { finish(true); }
      function onCancel() { finish(false); }
      confirmation.addEventListener('close', onClose);
      confirmAccept.addEventListener('click', onAccept);
      confirmCancel.addEventListener('click', onCancel);
      try {
        confirmation.showModal();
        confirmCancel.focus();
      } catch (e) {
        finish(false);
      }
    });
  }
  async function action(verb) {
    if(busy) return;
    if (verb === 'start' && !(await askToStart())) return;
    busy=true;start.disabled=stop.disabled=true;showError(verb==='start'?'正在等待任务结束并启动图形浏览器…':'正在关闭图形浏览器并恢复监控…');
    try {render(await api(verb,'POST'));showError('');}
    catch(e){showError(e.message);await refresh();}
    finally{busy=false;await refresh();}
  }
  start.addEventListener('click',()=>action('start'));
  stop.addEventListener('click',()=>action('stop'));
  refresh();
  setInterval(()=>{if(!busy)refresh();},5000);
})();
