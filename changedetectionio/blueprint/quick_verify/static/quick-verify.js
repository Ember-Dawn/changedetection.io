(() => {
'use strict';
const $ = id => document.getElementById(id);
const cfg = window.quickVerifyConfig;
const screen = $('qv-screen'), img = $('qv-frame');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let currentUrl = null, running = 0, scale = 1;
const contacts = new Map();
let gesture = null, longPress = null, remoteDown = false, downPoint = null;
let pendingMove = null, moveTask = null;
const message = text => { $('qv-message').textContent = text; };
const buttonState = () => {
  for (const id of ['qv-send','qv-enter','qv-scroll-up','qv-scroll-down','qv-reload','qv-back','qv-close','qv-finish']) $(id).disabled = !core.active() || core.state().busy || (cfg.testMode && id === 'qv-close');
  $('qv-connection').textContent = core.active() ? '● 已连接' : '○ 未连接';
};
function showOccupied(data) {
  $('qv-occupied').hidden = !(data && (data.active || data.opening));
  $('qv-resume').hidden = !data || !data.owned || data.watch_uuid !== cfg.watchUuid;
  if (data && data.active) $('qv-occupied-text').textContent = data.owned
    ? '已有你创建的人工会话。仅支持恢复同一个 Watch，其他会话请在完整 WebUI 中管理。'
    : '人工浏览器由其他设备占用。可在完整 WebUI 中强制结束会话。';
  else $('qv-occupied-text').textContent = '浏览器会话正在准备或清理，请稍后刷新。';
}
function cleanup() {
  running++;
  releaseRemote();
  resetGesture();
  if (currentUrl) URL.revokeObjectURL(currentUrl);
  currentUrl = null; img.hidden = true; img.removeAttribute('src'); $('qv-placeholder').hidden = false;
  buttonState();
}
const core = window.ManualBrowser.createCore({api: cfg.api, csrf: cfg.csrf}, {
 message,
 busy:buttonState,
 inspected:showOccupied,
 connected() { showOccupied(null); $('qv-connect').hidden = true; buttonState(); message(''); startFrames(); },
 disconnected(reason) {cleanup(); $('qv-connect').hidden = !(cfg.needsAttention || cfg.testMode); message(reason && /过期|错误|失败|占用|异常/.test(reason) ? reason : '');},
 ended({path,result}) {message(path === 'finish' && !result.recheck_queued ? '操作已完成，但检查未入队，请到 Watch 列表确认' : '');}
});
function refreshImage(blob, generation) {
  if (generation !== running || !core.active()) return;
  const url = URL.createObjectURL(blob);
  img.onload = () => {
    if (generation !== running) {URL.revokeObjectURL(url); return;}
    if (currentUrl) URL.revokeObjectURL(currentUrl);
    currentUrl = url;
    $('qv-placeholder').hidden = true; img.hidden = false;
  };
  img.onerror = () => URL.revokeObjectURL(url);
  img.src = url;
}
async function startFrames() {
  const generation = ++running;
  while (generation === running && core.active()) {
    if (document.hidden) {await delay(800); continue;}
    try {
      const ticket = core.snapshot();
      const response = await core.request('frame?session=' + encodeURIComponent(ticket.token));
      const blob = await response.blob();
      if (core.valid(ticket)) refreshImage(blob, generation);
    } catch (err) {
      if (core.terminal(err)) {core.disconnect('会话已过期或被 WebUI 结束'); break;}
      message('画面暂不可用，正在重试：' + err.message);
      await delay(1200);
    }
    await delay(450);
  }
}
async function initialConnect() {
  const status = await core.inspect();
  if (!status || status.active || status.opening) return;
  if (!cfg.testMode && !cfg.needsAttention) {message('该监控当前没有待处理的人机验证；如仍需操作，请手动连接。'); $('qv-connect').hidden = false; return;}
  await core.connect('', cfg.watchUuid, {test_mode: !!cfg.testMode});
}
function point(event) {
  const rect = img.getBoundingClientRect();
  if (img.hidden || !rect.width || !rect.height || !img.naturalWidth || !img.naturalHeight) return null;
  return {x: Math.max(0, Math.min(img.naturalWidth, (event.clientX - rect.left) / rect.width * img.naturalWidth)),
          y: Math.max(0, Math.min(img.naturalHeight, (event.clientY - rect.top) / rect.height * img.naturalHeight))};
}
function action(name,args={}) {return core.send(name,args);}
const clamp = (value, lo, hi) => Math.max(lo, Math.min(hi, value));
function fit() {scale=1;img.style.width='100%';screen.scrollLeft=0;screen.scrollTop=0;}
// Keep the screenshot point under the two-finger midpoint stationary as the image grows.
function zoomAt(nextScale, x, y) {
  const rect=screen.getBoundingClientRect();
  const oldScale=scale;
  nextScale=clamp(nextScale,1,4);
  if (nextScale===oldScale) return;
  const localX=x-rect.left, localY=y-rect.top;
  const imageX=(screen.scrollLeft+localX)/oldScale;
  const imageY=(screen.scrollTop+localY)/oldScale;
  scale=nextScale;
  img.style.width=(scale*100)+'%';
  screen.scrollLeft=imageX*scale-localX;
  screen.scrollTop=imageY*scale-localY;
}
function clearHold() {if(longPress!==null)clearTimeout(longPress);longPress=null;}
function resetGesture() {clearHold();contacts.clear();gesture=null;pendingMove=null;}
// ManualBrowser core serializes all remote commands. Coalesce intermediate moves
// and always flush the last move before releasing the remote mouse button.
function flushMoves() {
  if (moveTask) return moveTask;
  moveTask=(async()=>{
    while(core.active() && pendingMove) {
      const p=pendingMove;pendingMove=null;
      await action('move',p);
    }
  })().finally(()=>{moveTask=null;});
  return moveTask;
}
function beginDrag(p) {
  if(!p || !core.active() || remoteDown) return;
  remoteDown=true;
  downPoint=p;
  action('down',p);
}
async function releaseRemote(p=downPoint) {
  clearHold();
  if(!remoteDown) return;
  remoteDown=false;
  if(p) pendingMove=p;
  try {await flushMoves();} finally {
    if(core.active() && p) await action('up',p);
    pendingMove=null;downPoint=null;
  }
}
function contact(event) {return {x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY};}
const length=(a,b)=>Math.hypot(a.x-b.x,a.y-b.y);
const middle=(a,b)=>({x:(a.x+b.x)/2,y:(a.y+b.y)/2});
screen.addEventListener('pointerdown',event=>{
  if(!core.active() || event.target!==img || (event.pointerType==='mouse' && event.button!==0))return;
  event.preventDefault();
  screen.focus({preventScroll:true});
  screen.setPointerCapture(event.pointerId);
  contacts.set(event.pointerId,contact(event));
  if(contacts.size===1) {
    gesture={type:'single',id:event.pointerId,origin:point(event),last:contact(event),moved:false,drag:false};
    {
      clearHold();
      longPress=setTimeout(()=>{
        if(gesture && gesture.type==='single' && contacts.size===1 && !gesture.drag) {
          gesture.drag=true;beginDrag(gesture.origin);
        }
      },300);
    }
  } else if(contacts.size===2) {
    clearHold();
    if(remoteDown)releaseRemote();
    const [a,b]=[...contacts.values()];
    gesture={type:'multi',distance:length(a,b),mid:middle(a,b)};
  }
});
screen.addEventListener('pointermove',event=>{
  if(!contacts.has(event.pointerId) || !core.active())return;
  event.preventDefault();
  const old=contacts.get(event.pointerId);
  contacts.set(event.pointerId,{...old,x:event.clientX,y:event.clientY});
  if(contacts.size===2 && gesture && gesture.type==='multi') {
    const [a,b]=[...contacts.values()], mid=middle(a,b), dist=length(a,b);
    // First pan the existing image; then zoom around the current midpoint.
    screen.scrollLeft-=mid.x-gesture.mid.x;
    screen.scrollTop-=mid.y-gesture.mid.y;
    if(gesture.distance>0) zoomAt(scale*dist/gesture.distance,mid.x,mid.y);
    gesture.mid=mid;gesture.distance=dist;
    return;
  }
  if(!gesture || gesture.type==='multi' || event.pointerId!==gesture.id)return;
  const travel=Math.hypot(event.clientX-old.startX,event.clientY-old.startY);
  if(travel>9 && !gesture.drag) {
    clearHold();gesture.moved=true;gesture.drag=true;beginDrag(gesture.origin);
  }
  if(gesture.drag) {
    const p=point(event);
    if(p) {downPoint=p;pendingMove=p;flushMoves();}
  }
});
function release(event,cancel=false) {
  if(!contacts.has(event.pointerId))return;
  const p=point(event)||downPoint;
  contacts.delete(event.pointerId);
  if(screen.hasPointerCapture && screen.hasPointerCapture(event.pointerId)) screen.releasePointerCapture(event.pointerId);
  if(gesture && gesture.type==='multi') {
    if(!contacts.size)resetGesture();
    return;
  }
  if(!gesture || event.pointerId!==gesture.id)return;
  const drag=gesture.drag, shouldClick=!cancel && gesture.type==='single' && !gesture.moved && !drag;
  clearHold();
  if(drag)releaseRemote(p);
  else if(shouldClick && p)action('click',p);
  resetGesture();
}
screen.addEventListener('pointerup',e=>release(e));
screen.addEventListener('pointercancel',e=>release(e,true));
screen.addEventListener('lostpointercapture',e=>{if(contacts.has(e.pointerId))release(e,true);});
screen.addEventListener('wheel',event=>{
  if(!core.active())return;
  event.preventDefault();
  if(event.ctrlKey) {zoomAt(scale*(event.deltaY>0?.9:1.1),event.clientX,event.clientY);return;}
  const p=point(event);if(p)action('scroll',{...p,dx:event.deltaX,dy:event.deltaY});
},{passive:false});
screen.addEventListener('keydown',event=>{
  if(!core.active()||event.ctrlKey||event.metaKey||event.altKey)return;
  if(event.key.length===1||['Enter','Tab','Backspace','Escape','ArrowUp','ArrowDown'].includes(event.key)) {
    event.preventDefault();action('key',{key:event.key===' '?'Space':event.key});
  }
});
$('qv-send').addEventListener('click',()=>{const el=$('qv-text');if(!el.value)return;const value=el.value;action('text',{text:value}).then(()=>{if(el.value===value)el.value='';});});
$('qv-enter').addEventListener('click',()=>action('key',{key:'Enter'}));
$('qv-reload').addEventListener('click',()=>action('refresh'));
$('qv-back').addEventListener('click',()=>action('back'));
$('qv-fit').addEventListener('click',fit);
// Explicit wheel actions avoid gesture-mode conflicts on mobile. Negative dy scrolls up.
function wheelStep(dy) {
  if (!core.active() || img.hidden) return;
  action('scroll', {x: img.naturalWidth / 2, y: img.naturalHeight / 2, dx: 0, dy});
}
$('qv-scroll-up').addEventListener('click', () => wheelStep(-300));
$('qv-scroll-down').addEventListener('click', () => wheelStep(300));
$('qv-close').addEventListener('click',()=>core.end('close'));
$('qv-finish').addEventListener('click',()=>{
  if(cfg.testMode){core.end('close');return;}
  if(window.confirm('完成操作并重新检查这个 Watch？'))core.end('finish');
});
$('qv-resume').addEventListener('click',async()=>{const data=await core.inspect();if(data&&data.active&&data.owned&&data.watch_uuid===cfg.watchUuid)core.resume(data.session);});
$('qv-check').addEventListener('click',()=>core.inspect());
$('qv-connect').addEventListener('click',()=>core.connect('',cfg.watchUuid,{test_mode:!!cfg.testMode}));
// A hidden tab or lock screen must not leave a held mouse button in the remote browser.
document.addEventListener('visibilitychange',()=>{
  if(document.hidden){releaseRemote();resetGesture();}
  else if(core.active())message('');
});
window.addEventListener('blur',()=>{releaseRemote();resetGesture();});
window.addEventListener('pagehide',()=>{releaseRemote();resetGesture();running++;if(currentUrl)URL.revokeObjectURL(currentUrl);});
// Suppress native long-press image menus and image drag, without affecting inputs.
for (const element of [screen, img]) {
  element.addEventListener('contextmenu', e => e.preventDefault());
  element.addEventListener('dragstart', e => e.preventDefault());
  element.addEventListener('selectstart', e => e.preventDefault());
}
buttonState();initialConnect();
})();
