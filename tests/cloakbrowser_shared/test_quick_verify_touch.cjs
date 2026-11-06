'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const script = fs.readFileSync(path.resolve(__dirname,'../../changedetectionio/blueprint/quick_verify/static/quick-verify.js'),'utf8');

function harness() {
  const actions=[];
  const elements = new Map();
  function element(id) {
    const handlers = {};
    return {
      id, handlers, hidden:false, value:'', disabled:false, style:{}, naturalWidth:1366, naturalHeight:900,
      scrollLeft:0,scrollTop:0,clientWidth:400,clientHeight:280, textContent:'',
      addEventListener(event,callback){(handlers[event] ||= []).push(callback);},
      trigger(name,e={}){for(const cb of handlers[name]||[])cb(e);},
      setAttribute(name,value){this[name]=value;},
      getBoundingClientRect() {
        const w=400*(parseFloat(elements.get('qv-frame')?.style.width||'100')/100);
        return this.id==='qv-frame'
          ? {left:-elements.get('qv-screen').scrollLeft,top:-elements.get('qv-screen').scrollTop,width:w,height:w*900/1366}
          : {left:0,top:0,width:400,height:280};
      },
      setPointerCapture(){},hasPointerCapture(){return false;},releasePointerCapture(){},focus(){},removeAttribute(){}
    };
  }
  for (const id of ['qv-screen','qv-frame','qv-send','qv-enter','qv-reload','qv-back','qv-close','qv-finish','qv-connection','qv-message','qv-placeholder','qv-occupied','qv-resume','qv-occupied-text','qv-connect','qv-check','qv-fit','qv-scroll-up','qv-scroll-down','qv-text']) elements.set(id,element(id));
  const document = {hidden:false,getElementById:id=>elements.get(id),addEventListener(){}};
  const window = {quickVerifyConfig:{api:'/manual-browser/',csrf:'x',watchUuid:'watch',testMode:true,needsAttention:false},addEventListener(){},ManualBrowser:{createCore(config,hooks){
    return {active:()=>true,state:()=>({busy:false}),send:(name,args)=>{actions.push([name,args]);return Promise.resolve();},inspect:()=>Promise.resolve({active:true}),};
  }}};
  const context={window,document,URL:{revokeObjectURL(){}},setTimeout,clearTimeout,console};
  vm.runInNewContext(script,context);
  const pointer=(type,id,x,y,extra={})=>elements.get('qv-screen').trigger(type,{pointerId:id,clientX:x,clientY:y,pointerType:'touch',target:elements.get('qv-screen'),preventDefault(){},...extra});
  return {actions,elements,pointer};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('two-finger pan moves the local viewport without remote scroll or clicks',async()=>{
  const h=harness();const s=h.elements.get('qv-screen');
  h.pointer('pointerdown',1,100,100);h.pointer('pointerdown',2,200,100);
  h.pointer('pointermove',2,260,100); // pinch to 160%
  assert.equal(h.elements.get('qv-frame').style.width,'160%');
  h.pointer('pointermove',1,70,100); // move center left
  assert.ok(s.scrollLeft>0,'panning must move the viewport');
  h.pointer('pointerup',1,70,100);h.pointer('pointerup',2,260,100);
  await tick();
  assert.deepEqual(h.actions.map(a=>a[0]),[]);
});
test('single finger drag preserves down, move, up order',async()=>{
  const h=harness();h.pointer('pointerdown',1,100,100);
  h.pointer('pointermove',1,130,105);h.pointer('pointermove',1,160,105);
  h.pointer('pointerup',1,160,105);
  await tick();await tick();await tick();
  assert.deepEqual(h.actions.map(a=>a[0]),['down','move','up']); // coalesced moves
});
test('cancel releases remote mouse but never produces a click',async()=>{
  const h=harness();h.pointer('pointerdown',1,100,100);h.pointer('pointermove',1,120,100);
  h.pointer('pointercancel',1,120,100);
  await tick();await tick();
  const names=h.actions.map(a=>a[0]);
  assert.equal(names[0],'down');assert.equal(names.at(-1),'up');assert.ok(!names.includes('click'));
});
test('click after zoom and pan uses the transformed image coordinates',async()=>{
  const h=harness(), s=h.elements.get('qv-screen');
  h.pointer('pointerdown',1,100,100);h.pointer('pointerdown',2,200,100);h.pointer('pointermove',2,300,100);
  h.pointer('pointerup',1,100,100);h.pointer('pointerup',2,300,100);
  s.scrollLeft=140;
  h.pointer('pointerdown',3,130,80);h.pointer('pointerup',3,130,80);
  await tick();
  const click=h.actions.find(x=>x[0]==='click');
  assert.ok(click);
  assert.ok(Math.abs(click[1].x-(270/800*1366))<1);
});
test('test mode secondary close button is disabled',()=>{
  const h=harness();assert.equal(h.elements.get('qv-close').disabled,true);
});

test('up and down icon buttons issue distinct remote wheel events',async()=>{
  const h=harness();
  h.elements.get('qv-frame').hidden=false;
  h.elements.get('qv-scroll-up').trigger('click');
  h.elements.get('qv-scroll-down').trigger('click');
  await tick();
  assert.deepEqual(h.actions.map(([name])=>name),['scroll','scroll']);
  assert.equal(h.actions[0][1].dy,-300);
  assert.equal(h.actions[1][1].dy,300);
  assert.equal(h.actions[0][1].dx,0);
});
test('native context menu and image dragging are prevented only on remote surface',()=>{
  const h=harness();
  for(const id of ['qv-screen','qv-frame']) {
    for(const name of ['contextmenu','dragstart','selectstart']) {
      let prevented=false;
      h.elements.get(id).trigger(name,{preventDefault(){prevented=true;}});
      assert.equal(prevented,true,`${id} ${name}`);
    }
  }
  assert.equal((h.elements.get('qv-text').handlers.contextmenu||[]).length,0);
});

test('native touch behavior is cancelled on the remote viewport',()=>{
  const h=harness(),surface=h.elements.get('qv-screen');
  h.elements.get('qv-frame').hidden=false;
  for(const type of ['touchstart','touchmove']) {
    let blocked=false;
    surface.trigger(type,{cancelable:true,preventDefault(){blocked=true;}});
    assert.equal(blocked,true);
  }
  assert.equal((h.elements.get('qv-text').handlers.touchstart||[]).length,0);
});
test('viewport remains the active pointer target',async()=>{
 const h=harness();
 h.pointer('pointerdown',1,90,90);h.pointer('pointerup',1,90,90);
 await tick();
 assert.ok(h.actions.some(([name])=>name==='click'));
});
