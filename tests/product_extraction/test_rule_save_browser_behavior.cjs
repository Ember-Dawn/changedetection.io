'use strict';
// DOM/fetch behavioral harness: no app runtime or external dependencies required.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../../changedetectionio/blueprint/product_extractors/static/product-extractors.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
function element(id) {
  const handlers = {};
  return {
    id, dataset: {}, value: '', hidden: false, disabled: false, textContent: '', className: '',
    classList: {add(){}, remove(){}, toggle(){return false;}},
    style: {}, children: [], files: [], attributes: {},
    addEventListener(type, cb) { (handlers[type] ||= []).push(cb); },
    async fire(type, extras = {}) { for(const cb of handlers[type] || []) await cb({preventDefault(){},stopPropagation(){},target:this,...extras}); },
    replaceChildren(...children) {this.children=children;},
    append(...children) {this.children.push(...children);},
    add(opt) {this.children.push(opt);},
    removeAttribute(){}, setAttribute(){}, focus(){doc.activeElement=this;},
  };
}
let doc;
async function setup({ initialRules, failList=false }) {
  const elements = new Map();
  const get = id => { if(!elements.has(id)) elements.set(id, element(id)); return elements.get(id); };
  doc = {
    activeElement: null,
    getElementById: get,
    contains: () => true,
    createElement: tag => element(tag),
  };
  get('px-confirm-dialog').hidden = true;
  get('px-root').dataset.apiBase = '/product-extractors/';
  get('px-root').dataset.csrf = 'test';
  const rules = new Map(initialRules.map(r=>[r.id, r]));
  const sent=[];
  let serverConflict=false;
  let forceRevisionConflict=false;
  async function fetch(url, init) {
    const route=String(url).split('/product-extractors/')[1];
    if (route==='api/list') return reply(failList?500:200,failList?{error:'offline'}:{rules:[...rules.values()].map(r=>({id:r.id,name:r.name,enabled:true,domains:['newegg.com'],revision:r.revision}))});
    if (route==='api/save') {
      const body=JSON.parse(init.body); sent.push(body);
      const current=rules.get(body.rule.id);
      if (serverConflict || (current && !body.overwrite))return reply(409,{error:'Rule ID already exists with different content; confirm overwrite', code:'RULE_ID_CONFLICT'});
      if(forceRevisionConflict)return reply(409,{error:'Rule changed since opening; reload before overwriting',code:'RULE_REVISION_CONFLICT'});
      if(current && current.revision!==body.expected_signature)return reply(409,{error:'Rule changed since opening; reload before overwriting',code:'RULE_REVISION_CONFLICT'});
      rules.set(body.rule.id,{...body.rule,revision:'rev2'});
      return reply(200,{rule:body.rule,status:current?'updated':'created'});
    }
    if(route.startsWith('api/'))return reply(200,rules.get(route.slice(4)));
    return reply(404,{error:'unknown'});
  }
  function reply(status,body) {return {ok:status<400,status,async json(){return body;}};}
  const context={document:doc,window:{addEventListener(){},CDSelect:null},fetch,Option:function(text,value){return {text,value}},console, navigator:{clipboard:{writeText:async()=>{}}}};
  vm.runInNewContext(script,context);
  await tick();await tick();
  return {get,sent,rules, async save(){await get('product-rule-save').fire('click');await tick();await tick();}, async select(id){get('product-rule-list').value=id;await get('product-rule-list').fire('change');await tick();}, async accept(){await get('px-confirm-dialog').fire('keydown',{key:'Enter',isComposing:false,keyCode:13});await tick();},setConflict(value){serverConflict=value;},setRevisionConflict(value){forceRevisionConflict=value;}};
}
(async()=>{
  const first=await setup({initialRules:[{id:'newegg-products',name:'Newegg',revision:'rev1',fields:{currency:{literal:'USD'}}}]});
  assert.equal(first.get('product-rule-list').children.length,2,'list initialized on initial load');
  await first.select('newegg-products');
  first.get('product-rule-json').value=JSON.stringify({id:'newegg-products',name:'Newegg',fields:{currency:{literal:'EUR'}}});
  await first.save();
  assert.equal(first.sent.length,1);
  assert.equal(first.sent[0].overwrite,true);
  assert.equal(first.sent[0].expected_signature,'rev1');
  assert.equal(first.get('px-confirm-dialog').hidden,true);
  assert.match(first.get('product-rule-message').textContent,/Updated/);

  const second=await setup({initialRules:[{id:'newegg-products',name:'Newegg',revision:'rev1'}]});
  second.get('product-rule-json').value=JSON.stringify({id:'newegg-products',name:'Different',fields:{currency:{literal:'USD'}}});
  const promise=second.get('product-rule-save').fire('click');
  await tick();
  assert.equal(second.get('px-confirm-dialog').hidden,false,'collision triggers dialog');
  await second.accept(); await promise; await tick();
  assert.equal(second.sent[0].overwrite,true);
  assert.equal(second.sent[0].expected_signature,'rev1');

  const third=await setup({initialRules:[{id:'newegg-products',name:'Newegg',revision:'rev1'}],failList:true});
  assert.equal(third.get('product-rule-save').disabled,true,'failed initial index must disable save');
  const fourth=await setup({initialRules:[{id:'newegg-products',name:'Newegg',revision:'rev1'}]});
  await fourth.select('newegg-products');
  fourth.setRevisionConflict(true);
  fourth.get('product-rule-json').value=JSON.stringify({id:'newegg-products',name:'Changed'});
  await fourth.save();
  assert.equal(fourth.sent.length,1,'revision conflict cannot auto retry');
  assert.match(fourth.get('product-rule-message').textContent,/Reload the rule/);
  assert.equal(fourth.get('px-confirm-dialog').hidden,true);

  const fifth=await setup({initialRules:[]});
  fifth.get('product-rule-json').value=JSON.stringify({id:'newegg-products',name:'New rule'});
  // Simulate a concurrent rule creation after the initial list loaded.
  fifth.rules.set('newegg-products',{id:'newegg-products',name:'Other editor',revision:'rev1'});
  const savePromise=fifth.get('product-rule-save').fire('click');
  await tick();await tick();
  assert.equal(fifth.get('px-confirm-dialog').hidden,false,'server 409 should surface custom dialog');
  await fifth.accept(); await savePromise;
  assert.equal(fifth.sent.length,2);
  assert.equal(fifth.sent[0].overwrite,false);
  assert.equal(fifth.sent[1].expected_signature,'rev1');
  assert.equal(fifth.sent[1].overwrite,true);
  console.log('PASS: initial index, first edited save, collision + Enter, failed index safety, revision conflict, server-side 409 recovery');
})().catch(err=>{console.error(err);process.exitCode=1;});
