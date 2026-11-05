'use strict';
// No Chromium needed: exercise the actual browser-side modules in an isolated JS VM.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const assets = path.resolve(__dirname, '../../changedetectionio/blueprint/manual_browser/static');
function deferred() {
  let resolve, reject;
  const promise = new Promise((a,b) => {resolve=a;reject=b;});
  return {promise,resolve,reject};
}
function setup(fetcher) {
  const handlers = {};
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) {
      elements.set(id, {
        id, hidden:false, value:'', disabled:false, textContent:'', classList:{toggle(){}}, style:{setProperty(){}},
        src:'', onload:null, onerror:null, isConnected:true,
        listeners:{},
        addEventListener(type,cb) { this.listeners[type] = cb; },
        removeAttribute(name) {delete this[name];},
        getBoundingClientRect() {return {top:50,left:10,right:810,bottom:610,width:800,height:560};},
        focus() {}, setPointerCapture() {}, releasePointerCapture() {},
        hasPointerCapture() {return false;}
      });
    }
    return elements.get(id);
  }
  let nextTimer = 0;
  const timers = new Map();
  const ctx = {
    console, Promise, Math, URL:{createObjectURL:()=>`blob:${Math.random()}`,revokeObjectURL:()=>{}},
    window:{ManualBrowser:{},innerHeight:900,addEventListener(type,cb){handlers[`window:${type}`]=cb;},removeEventListener(){}},
    document:{hidden:false,activeElement:null,getElementById:element,addEventListener(type,cb){handlers[`document:${type}`]=cb;}},
    fetch:fetcher,
    setTimeout(fn,ms){const id=++nextTimer;timers.set(id,{fn,ms});return id;},
    clearTimeout(id){timers.delete(id);},
  };
  vm.createContext(ctx);
  function load(name) { vm.runInContext(fs.readFileSync(path.join(assets,name),'utf8'),ctx,{filename:name}); }
  function fireTimers() {const jobs=Array.from(timers.values());timers.clear();jobs.forEach(({fn})=>fn());}
  return {ctx,element,load,handlers,timers,fireTimers};
}
function ok(data={}) {return {ok:true,status:200,json:async()=>data,text:async()=>JSON.stringify(data),blob:async()=>({})};}
function error(code,msg) {return {ok:false,status:code,text:async()=>JSON.stringify({error:msg})};}

// The session token belongs to exactly one tab and must change on resume.
test('session open/resume/close use authenticated same-origin requests',async()=>{
  const calls=[];
  const sim=setup(async (url,opt)=>{
    calls.push({url,opt});
    if(url.endsWith('/open'))return ok({session:'first',generation:4});
    if(url.endsWith('/resume'))return ok({session:'rotated',generation:4});
    if(url.endsWith('/close'))return ok({closed:true});
    return ok({active:false});
  });
  sim.load('manual-core.js');
  const events=[];
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/',csrf:'test-token'},
    {connected:()=>events.push('connected'),disconnected:()=>events.push('disconnected')});
  await core.connect('https://example.org','');
  assert.equal(core.state().token,'first');
  await core.end('close');
  assert.equal(core.active(),false);
  await core.resume('first');
  assert.equal(core.state().token,'rotated');
  assert.deepEqual(events,['connected','disconnected','connected']);
  assert.ok(calls.every(c=>c.opt.credentials==='same-origin'));
  assert.ok(calls.every(c=>c.opt.headers['X-CSRFToken']==='test-token'));
});

test('stale lookup result never overwrites a newer connection',async()=>{
  const pending=deferred();
  const sim=setup(async url => url.endsWith('/current') ? pending.promise : ok({session:'new',generation:1}));
  sim.load('manual-core.js');
  const observations=[];
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'},{inspected:x=>observations.push(x)});
  const inspection=core.inspect();
  await core.connect('https://example.org','');
  pending.resolve(ok({active:true,owned:true,session:'old'}));
  await inspection;
  assert.equal(observations.length,0);
  assert.equal(core.state().token,'new');
});

test('queued actions are ordered and a failed action does not poison later actions',async()=>{
  let count=0;
  const events=[];
  const sim=setup(async(url,opt)=>{
    if(url.endsWith('/open'))return ok({session:'ready',generation:2});
    if(url.endsWith('/action')) {
      const data=JSON.parse(opt.body);events.push(data.action);
      if(++count===1)return error(503,'temporary failure');
    }
    return ok();
  });
  sim.load('manual-core.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'});
  await core.connect('https://example.org','');
  await Promise.all([core.send('move',{x:1,y:1}),core.send('up',{x:1,y:1})]);
  assert.deepEqual(events,['move','up']);
});

test('terminal frame status ends session; transient HTTP 500 remains retryable',async()=>{
  let frameCode=500, disconnected=0;
  const sim=setup(async url=>{
    if(url.endsWith('/open'))return ok({session:'x',generation:1});
    if(url.includes('/frame?'))return error(frameCode,'browser loading');
    return ok({generation:1,url:'https://test.org',seconds_remaining:900});
  });
  sim.load('manual-core.js');sim.load('manual-stream.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'},
    {disconnected:()=>disconnected++});
  const stream=sim.ctx.window.ManualBrowser.createStream(core,{});
  await core.connect('https://test.org','');
  stream.start();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(core.active(),true);
  assert.equal(disconnected,0);
  frameCode=409;
  sim.fireTimers();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(core.active(),false);
  assert.equal(disconnected,1);
  stream.stop();
});

test('coordinate translation uses rendered image rectangle and viewport size',()=>{
  const sim=setup(async()=>ok());
  sim.load('manual-input.js');
  const img=sim.element('manual-frame');
  img.getBoundingClientRect=()=>({left:100,top:40,right:500,bottom:240,width:400,height:200});
  const input=sim.ctx.window.ManualBrowser.createInput({active:()=>true},{},{viewport:()=>({width:800,height:400})});
  const result=input.point({clientX:300,clientY:140});
  assert.equal(result.x,400);
  assert.equal(result.y,200);
  assert.equal(input.point({clientX:10,clientY:20}),null);
});

test('terminal API errors carry numeric HTTP status, not only a message regex',async()=>{
  const sim=setup(async()=>error(409,'Manual session has ended or belongs to another login'));
  sim.load('manual-core.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'});
  let caught;
  try {await core.api('current');}catch(e){caught=e;}
  assert.equal(caught.status,409);
  assert.equal(core.terminal(caught),true);
  assert.equal(core.terminal({status:500,message:'navigation is in progress'}),false);
});

test('layout fixed default uses 1366 x 900 and retains its session',async()=>{
  const sim=setup(async()=>ok());
  sim.load('manual-layout.js');
  const sent=[];
  const core={active:()=>true,snapshot:()=>({token:'t',epoch:1}),valid:()=>true,
              send:async(action,args)=>{sent.push({action,args});}};
  const layout=sim.ctx.window.ManualBrowser.createLayout(core);
  layout.init();
  await layout.start();
  assert.equal(sent[0].action,'resize');
  assert.equal(sent[0].args.width,1366);
  assert.equal(sent[0].args.height,900);
  assert.equal(layout.viewport().width,1366);
  assert.equal(layout.viewport().height,900);
  layout.shutdown();
});

test('input sends mouse-up after lost pointer capture',async()=>{
  const sim=setup(async()=>ok());
  sim.load('manual-input.js');
  const sent=[];
  const core={active:()=>true,send:async (type,args)=>{sent.push({type,args});},snapshot:()=>({}),valid:()=>true};
  const input=sim.ctx.window.ManualBrowser.createInput(core,{}, {viewport:()=>({width:800,height:560})});
  input.init();
  const wrap=sim.element('manual-frame-wrap');
  const img=sim.element('manual-frame');
  wrap.listeners.pointerdown({button:0,target:img,clientX:400,clientY:300,pointerId:1,preventDefault(){}});
  wrap.listeners.lostpointercapture({});
  await new Promise(r=>setImmediate(r));
  assert.deepEqual(sent.map(x=>x.type),['down','move','up']);
});

test('all frontend modules initialize in template load order without a bundler',async()=>{
  const sim=setup(async url=>url.endsWith('/current') ? ok({active:false,opening:false}) : ok());
  sim.ctx.window.manualBrowserConfig={api:'/manual-browser/',csrf:'test'};
  sim.element('manual-url').value='https://example.net';
  for(const file of ['manual-core.js','manual-transport.js','manual-stream.js','manual-layout.js','manual-input.js','manual-browser.js']) sim.load(file);
  assert.ok(sim.element('manual-open').listeners.click);
  assert.ok(sim.element('manual-back').listeners.click);
  assert.ok(sim.element('manual-refresh').listeners.click);
  assert.ok(sim.handlers['document:visibilitychange']);
  await new Promise(r=>setImmediate(r));
  assert.equal(sim.element('manual-existing').hidden,true);
  sim.handlers['window:pagehide']();
});

test('interaction refresh coalesces while a screenshot HTTP request is pending',async()=>{
  const held=deferred();
  let frames=0;
  const sim=setup(async url=>{
    if(url.endsWith('/open')) return ok({session:'connected',generation:1});
    if(url.includes('/frame?')) { frames++; return frames===1 ? held.promise : ok(); }
    return ok({generation:1,url:'https://example.net',seconds_remaining:900,profile_lock_held:true});
  });
  sim.load('manual-core.js'); sim.load('manual-stream.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'});
  const stream=sim.ctx.window.ManualBrowser.createStream(core,{});
  await core.connect('https://example.net','');
  stream.start();
  stream.requestRefresh(); stream.requestRefresh();
  assert.equal(frames,1,'requests must remain single-flight');
  held.resolve(ok());
  await new Promise(resolve=>setImmediate(resolve));
  const frameTimer=Array.from(sim.timers.values()).find(x=>x.ms===100);
  assert.ok(frameTimer,'interaction must advance next frame to 100ms');
  stream.stop();
});

test('input actions tell frame scheduler after remote command completes',async()=>{
  const sim=setup(async()=>ok()); sim.load('manual-input.js');
  const order=[];
  const core={active:()=>true,send:async()=>{order.push('remote');},snapshot:()=>({token:'t'}),valid:()=>true};
  const stream={interaction:()=>order.push('input'),actionCompleted:()=>order.push('refresh')};
  const input=sim.ctx.window.ManualBrowser.createInput(core,stream,{viewport:()=>({width:800,height:560})});
  input.init();
  sim.element('manual-enter').listeners.click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(order,['input','remote','refresh']);
});

test('old frame cannot block fresh screenshot after stream restart',async()=>{
  const held=deferred();
  let frames=0;
  const sim=setup(async url=>{
    if(url.endsWith('/open')) return ok({session:'ready',generation:1});
    if(url.includes('/frame?')){frames++;return frames===1?held.promise:ok();}
    return ok({generation:1,url:'https://example.org',seconds_remaining:900});
  });
  sim.load('manual-core.js');sim.load('manual-stream.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'});
  const stream=sim.ctx.window.ManualBrowser.createStream(core,{});
  await core.connect('https://example.org','');
  stream.start();
  stream.stop();
  stream.start();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(frames,2,'stale request cannot block a new stream');
  held.resolve(ok());
  await new Promise(resolve=>setImmediate(resolve));
  stream.shutdown();
});

test('Socket.IO input is ordered and never replays unacknowledged actions on failure', async()=>{
  const sim=setup(async url=>url.endsWith('/open') ? ok({session:'socket-test',generation:7}):ok());
  sim.load('manual-core.js');
  sim.load('manual-transport.js');
  const sockets=[];
  sim.ctx.window.io = (namespace, options) => {
    const events = {};
    const socket = {
      namespace, options, events, disconnected:false,
      on(name, fn) {events[name]=fn;},
      removeAllListeners() {Object.keys(events).forEach(key=>delete events[key]);},
      disconnect() {this.disconnected=true;},
      emit(name, payload, ack) {if(name==='action') { calls.push(payload); ack({ok:true,seq:payload.seq,result:{ok:true}}); }}
    };
    sockets.push(socket);
    return socket;
  };
  const calls=[];
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/',csrf:'csrf'});
  await core.connect('https://example.org','');
  const transport=sim.ctx.window.ManualBrowser.createTransport(core,{csrf:'csrf'},{});
  core.setTransport(transport);
  transport.start();
  assert.equal(sockets.length,2);
  assert.equal(sockets[0].options.transports[0],'websocket');
  sockets[0].events.connect(); sockets[1].events.connect();
  assert.equal(transport.isActive(),true);
  await core.send('move',{x:10,y:20},true);
  await core.send('down',{x:10,y:20},true);
  assert.deepEqual(calls.map(x=>x.seq),[1,2]);
  sockets[0].events.disconnect();
  assert.equal(transport.isActive(),false);
  assert.ok(sockets.every(socket=>socket.disconnected));
});

test('Socket.IO missing uses original HTTP transport without opening sockets',async()=>{
  const calls=[];
  const sim=setup(async (url,opt)=>{calls.push(url);return url.endsWith('/open')?ok({session:'s',generation:1}):ok({ok:true});});
  sim.load('manual-core.js'); sim.load('manual-transport.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/',csrf:'test'});
  await core.connect('https://example.org','');
  const transport=sim.ctx.window.ManualBrowser.createTransport(core,{csrf:'test'});
  core.setTransport(transport);
  transport.start();
  await core.send('move',{x:1,y:2},true);
  assert.equal(transport.isActive(),false);
  assert.ok(calls.some(url=>url.endsWith('/action')));
});

test('status exposes Page navigator fields and copy button only when UA exists',async()=>{
  const sim=setup(async url=>url.endsWith('/open') ? ok({session:'diag',generation:1}) : ok({
    generation:1,url:'https://example.net',seconds_remaining:899,
    user_agent:'Mozilla/5.0 TestChromium',platform:'Linux x86_64',
    width:1366,height:900,device_pixel_ratio:1.25,
    cookie_count:0,local_storage_keys:0,profile_lock_held:true
  }));
  sim.load('manual-core.js'); sim.load('manual-stream.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'});
  const stream=sim.ctx.window.ManualBrowser.createStream(core,{});
  await core.connect('https://example.net','');
  stream.start();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(sim.element('manual-ua').textContent,'Mozilla/5.0 TestChromium');
  assert.equal(sim.element('manual-platform').textContent,'Linux x86_64');
  assert.equal(sim.element('manual-viewport').textContent,'1366 × 900');
  assert.equal(sim.element('manual-dpr').textContent,'1.25');
  assert.equal(sim.element('manual-copy-ua').disabled,false);
  stream.stop();
  assert.equal(sim.element('manual-ua').textContent,'—');
  assert.equal(sim.element('manual-copy-ua').disabled,true);
});

test('WebSocket JPEG metadata is shown without treating screenshot time as network RTT',async()=>{
  const sim=setup(async url=>url.endsWith('/open') ? ok({session:'ws',generation:1}) : ok({generation:1,seconds_remaining:800}));
  sim.ctx.Blob=class {constructor(chunks){this.size=chunks[0].byteLength||chunks[0].length||0;}};
  sim.load('manual-core.js');sim.load('manual-stream.js');
  const core=sim.ctx.window.ManualBrowser.createCore({api:'/manual-browser/'});
  const stream=sim.ctx.window.ManualBrowser.createStream(core,{});
  await core.connect('https://example.net','');
  const transport={isActive:()=>true,isConnecting:()=>false,close(){},interaction(){},view(){},start(){}};
  stream.setTransport(transport);
  stream.start();
  let acknowledgements=0;
  stream.socketFrame({seq:1,jpeg:new Uint8Array(2048),capture_ms:181,screenshot_ms:140,
    dispatch_ms:41,bytes:2048,previous_ack_ms:77},()=>acknowledgements++);
  sim.element('manual-frame').onload();
  assert.equal(acknowledgements,1);
  assert.equal(sim.element('manual-frame-latency').textContent,'181 ms 服务端');
  assert.equal(sim.element('manual-screenshot-ms').textContent,'140 ms');
  assert.equal(sim.element('manual-dispatch-ms').textContent,'41 ms');
  assert.equal(sim.element('manual-frame-bytes').textContent,'2 KiB');
  assert.equal(sim.element('manual-ack-ms').textContent,'77 ms');
  stream.shutdown();
});
