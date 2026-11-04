'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.resolve(__dirname,'../../changedetectionio/blueprint/manual_browser/static/manual-layout.js'),'utf8');

function harness(savedMode) {
  const events = new Map();
  const storage = new Map(savedMode ? [['changedetection.manual-viewport-mode',savedMode]] : []);
  const actions = [];
  const root = {style:{},getBoundingClientRect:()=>({top:70})};
  const wrap = {getBoundingClientRect:()=>({width:1000,height:650})};
  const ctx = {
    document:{getElementById(id) {return id==='manual-browser-root'?root:wrap;}},
    window:{ManualBrowser:{},innerHeight:850,addEventListener:(k,cb)=>events.set(k,cb),removeEventListener:()=>{}},
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v)},
    setTimeout:cb=>{events.set('timeout',cb);return 1;},clearTimeout:()=>{},
    ResizeObserver:class{observe(){}disconnect(){}}
  };
  vm.createContext(ctx);vm.runInContext(source,ctx);
  const core={active:()=>true,snapshot:()=>({token:'t'}),valid:()=>true,
    send:async(action,data)=>{actions.push({...data});}};
  const layout=ctx.window.ManualBrowser.createLayout(core);
  layout.init();
  return {layout,events,actions,storage};
}
test('fixed mode remains 1366x768 regardless of container size',async()=>{
  const sim=harness();assert.equal(sim.layout.currentMode(),'fixed');
  await sim.layout.start();
  assert.equal(sim.actions.length,1);
  assert.equal(sim.actions[0].width,1366);
  assert.equal(sim.actions[0].height,768);
  sim.layout.schedule();
  assert.equal(sim.events.has('timeout'),false);
});
test('follow-window sets per-page viewport and persists preference',async()=>{
  const sim=harness();
  await sim.layout.start();
  sim.layout.setMode('window');
  sim.events.get('timeout')();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(sim.layout.currentMode(),'window');
  assert.equal(sim.actions.at(-1).width,998);
  assert.equal(sim.actions.at(-1).height,648);
  assert.equal(sim.storage.get('changedetection.manual-viewport-mode'),'window');
});
test('restores prior follow-window preference without persisting session token',async()=>{
  const sim=harness('window');
  await sim.layout.start();
  assert.equal(sim.actions[0].width,998);
  assert.equal(sim.storage.size,1);
});
