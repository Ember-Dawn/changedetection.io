(() => {
'use strict';
const $ = id => document.getElementById(id);
const cfg = window.quickVerifyConfig;
const screen = $('qv-screen'), img = $('qv-frame');
let currentUrl = null, running = 0, busyFrame = false, scale = 1;
let pointer = new Map(), longPress = null, dragging = false, lastPoint = null, pinchDistance = 0, pinchScale = 1, twoFingerY = 0, multiTouch = false, moved = false;
const message = text => { $('qv-message').textContent = text; };
const buttonState = () => {
  for (const id of ['qv-send','qv-enter','qv-reload','qv-back','qv-close','qv-finish']) $(id).disabled = !core.active() || core.state().busy;
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
  if (currentUrl) URL.revokeObjectURL(currentUrl);
  currentUrl = null; img.hidden = true; img.removeAttribute('src'); $('qv-placeholder').hidden = false;
  buttonState();
}
const core = window.ManualBrowser.createCore({api: cfg.api, csrf: cfg.csrf}, {
 message,
 busy:buttonState,
 inspected:showOccupied,
 connected() {showOccupied(null); $('qv-connect').hidden = true; buttonState(); message('已连接，可以操作验证页面'); startFrames();},
 disconnected(reason) {cleanup(); $('qv-connect').hidden = !cfg.needsAttention; message(reason || '会话已结束');},
 ended({path,result}) {message(path === 'finish' ? (result.recheck_queued ? '已安排重新检查' : '操作已完成，但检查未入队，请到 Watch 列表确认') : '已退出人工操作');}
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
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function initialConnect() {
  const status = await core.inspect();
  if (!status) return;
  if (status.active || status.opening) return;
  if (!cfg.needsAttention) { message('该监控当前没有待处理的人机验证；如仍需操作，请手动连接。'); $('qv-connect').hidden = false; return; }
  await core.connect('', cfg.watchUuid);
}
function point(event) {
  const rect = img.getBoundingClientRect();
  if (img.hidden || rect.width <= 0 || rect.height <= 0) return null;
  const x = (event.clientX - rect.left) / rect.width * img.naturalWidth;
  const y = (event.clientY - rect.top) / rect.height * img.naturalHeight;
  return {x:Math.max(0,Math.min(img.naturalWidth,x)),y:Math.max(0,Math.min(img.naturalHeight,y))};
}
function action(name,args={}) {return core.send(name,args);}
function updateZoom() { img.style.width = Math.round(scale*100)+'%'; }
function resetTouch() {clearTimeout(longPress);longPress=null;pointer.clear();dragging=false;lastPoint=null;pinchDistance=0;multiTouch=false;moved=false;}
function distance(a,b) {return Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY);}
function centerY(a,b) {return (a.clientY+b.clientY)/2;}
screen.addEventListener('pointerdown', event => {
  if (!core.active() || event.target !== img) return;
  event.preventDefault(); screen.setPointerCapture(event.pointerId);
  pointer.set(event.pointerId,{clientX:event.clientX,clientY:event.clientY,startX:event.clientX,startY:event.clientY});
  if (pointer.size === 1) {multiTouch=false;moved=false;}
  if (pointer.size===1) {
    lastPoint = point(event);
    longPress = setTimeout(()=>{if (pointer.size===1 && lastPoint){dragging=true;action('down',lastPoint);}},420);
  } else if (pointer.size===2) {
    multiTouch=true;clearTimeout(longPress);longPress=null;
    if (dragging && lastPoint) action('up',lastPoint);
    dragging=false;
    const values=[...pointer.values()];pinchDistance=distance(...values);pinchScale=scale;twoFingerY=centerY(...values);
  }
});
screen.addEventListener('pointermove',event=>{
  if (!pointer.has(event.pointerId) || !core.active()) return;
  event.preventDefault();const existing=pointer.get(event.pointerId);
  pointer.set(event.pointerId,{...existing,clientX:event.clientX,clientY:event.clientY});
  if(pointer.size===2){
    const values=[...pointer.values()], next=distance(...values), cy=centerY(...values);
    if(pinchDistance>0 && Math.abs(next-pinchDistance)>12) {scale=Math.max(1,Math.min(3,pinchScale*next/pinchDistance));updateZoom();}
    else if(Math.abs(cy-twoFingerY)>5){
      const rect=img.getBoundingClientRect();
      action('scroll',{x:img.naturalWidth/2,y:img.naturalHeight/2,dx:0,dy:(twoFingerY-cy)*img.naturalHeight/Math.max(rect.height,1)});
      twoFingerY=cy;
    }
    return;
  }
  if(Math.hypot(event.clientX-existing.startX,event.clientY-existing.startY)>12 && !dragging){moved=true;clearTimeout(longPress);longPress=null;}
  if(dragging){lastPoint=point(event);if(lastPoint)action('move',lastPoint);}
});
function release(event) {
 if(!pointer.has(event.pointerId))return;
 const two=pointer.size>1;
 pointer.delete(event.pointerId);clearTimeout(longPress);longPress=null;
 if(two || multiTouch){if(pointer.size===0)resetTouch();return;}
 const p=point(event)||lastPoint;
 if(dragging){if(p)action('up',p);}
 else if(p && !moved){action('click',p);}
 resetTouch();
}
screen.addEventListener('pointerup',release);
screen.addEventListener('pointercancel',event=>{if(dragging&&lastPoint)action('up',lastPoint);release(event);});
screen.addEventListener('wheel',event=>{if(!core.active())return;event.preventDefault(); const p=point(event);if(p)action('scroll',{...p,dx:event.deltaX,dy:event.deltaY});},{passive:false});
screen.addEventListener('keydown',event=>{if(!core.active()||event.ctrlKey||event.metaKey||event.altKey)return;if(event.key.length===1||['Enter','Tab','Backspace','Escape','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();action('key',{key:event.key===' '?'Space':event.key});}});
$('qv-send').addEventListener('click',()=>{const el=$('qv-text');if(!el.value)return;const value=el.value;action('text',{text:value}).then(()=>{if(el.value===value)el.value='';});});
$('qv-enter').addEventListener('click',()=>action('key',{key:'Enter'}));
$('qv-reload').addEventListener('click',()=>action('refresh'));
$('qv-back').addEventListener('click',()=>action('back'));
$('qv-fit').addEventListener('click',()=>{scale=1;updateZoom();screen.scrollTop=0;screen.scrollLeft=0;});
$('qv-close').addEventListener('click',()=>core.end('close'));
$('qv-finish').addEventListener('click',()=>{if(window.confirm('完成操作并重新检查这个 Watch？'))core.end('finish');});
$('qv-resume').addEventListener('click',async()=>{const data=await core.inspect();if(data&&data.active&&data.owned&&data.watch_uuid===cfg.watchUuid)core.resume(data.session);});
$('qv-check').addEventListener('click',()=>core.inspect());
$('qv-connect').addEventListener('click',()=>core.connect('',cfg.watchUuid));
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&core.active())message('正在恢复浏览器画面…');});
window.addEventListener('pagehide',()=>{running++;if(currentUrl)URL.revokeObjectURL(currentUrl);});
buttonState();initialConnect();
})();
