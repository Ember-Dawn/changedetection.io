const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const src = fs.readFileSync(path.join(__dirname, '../../changedetectionio/static/js/modal.js'), 'utf8');

function harness() {
  const buttons = new Map();
  const dialog = {
    closed: 0, removed: 0, listeners: {}, attrs: {},
    setAttribute(k,v) { this.attrs[k]=v; },
    querySelector(selector) {
      if (!buttons.has(selector)) {
        const b = {disabled:false, handlers:{}, addEventListener(type,fn) { this.handlers[type]=fn; },
          focus(){}, click(){if (!this.disabled) return this.handlers.click();}};
        if (selector === '.modal-body') b.textContent='';
        buttons.set(selector,b);
      }
      return buttons.get(selector);
    },
    addEventListener(type,handler) {this.listeners[type]=handler;},
    showModal(){},close(){this.closed++;},remove(){this.removed++;},
    getBoundingClientRect(){return {top:10,left:10,right:200,bottom:200};},
  };
  const document = {
    body:{appendChild(){ }},
    createElement(tag){return tag === 'dialog' ? dialog : {textContent:'',innerHTML:''};},
  };
  const context = {
    document,window:{},setTimeout(fn){fn();},
    $(){return {ready(){},on(){}};},
  };
  vm.runInNewContext(src, context);
  return {dialog,buttons,modal:context.window.ModalDialog};
}

const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('simple modal double confirm closes and calls callback once', async()=>{
 const h=harness();let count=0;
 const result=h.modal.confirm({onConfirm(){count++;}});
 const yes=h.buttons.get('[data-action="confirm"]');
 yes.click();yes.click();
 assert.equal(await result,true);
 assert.equal(count,1);
 assert.equal(h.dialog.closed,1);
});
test('waiting modal remains open, disabled, until server promise resolves', async()=>{
 const h=harness();let finish;
 const wait=new Promise(resolve=>finish=resolve);
 const result=h.modal.confirm({waitForCompletion:true,onConfirm(){return wait;}});
 const yes=h.buttons.get('[data-action="confirm"]');
 const no=h.buttons.get('[data-action="cancel"]');
 yes.click();
 assert.equal(yes.disabled,true);
 assert.equal(no.disabled,true);
 assert.equal(h.dialog.closed,0);
 yes.click();no.click();
 assert.equal(h.dialog.closed,0);
 finish();await flush();
 assert.equal(await result,true);
 assert.equal(h.dialog.closed,1);
});
test('failed server action keeps modal open with retry',async()=>{
 const h=harness();let count=0;
 const result=h.modal.confirm({waitForCompletion:true,onConfirm(){count++;if(count===1) return Promise.reject(Error('failed'));}});
 const yes=h.buttons.get('[data-action="confirm"]');
 yes.click();await flush();
 assert.equal(h.dialog.closed,0);
 assert.equal(yes.disabled,false);
 assert.match(h.buttons.get('.modal-body').textContent,/failed/);
 yes.click();await flush();
 assert.equal(await result,true);
 assert.equal(count,2);
 assert.equal(h.dialog.closed,1);
});
