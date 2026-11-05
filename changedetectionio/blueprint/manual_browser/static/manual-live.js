/* Live desktop state/actions are independent of the screenshot manual session. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const start = $('manual-live-start'), stop = $('manual-live-stop');
  if (!start || !stop) return;
  const status = $('manual-live-status'), message = $('manual-live-message');
  const frame = $('manual-live-frame'), iframe = $('manual-live-iframe');
  const popup = $('manual-live-popup'), shell = document.querySelector('.manual-browser-shell');
  const confirmation = $('manual-live-confirm');
  const confirmAccept = $('manual-live-confirm-accept');
  const confirmCancel = $('manual-live-confirm-cancel');
  const csrf = $('manual-csrf').value;
  const root = window.manualBrowserConfig.api.replace(/\/$/, '');
  let busy = false, lastPhase = null;
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
    start.hidden=!idle; stop.hidden=!(ours&&(active||s.phase==='error'));
    start.disabled=busy;stop.disabled=busy;
    popup.hidden=!(ours&&active);
    frame.hidden=!(ours&&active);
    shell.hidden=active || (ours&&s.phase==='error');
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
