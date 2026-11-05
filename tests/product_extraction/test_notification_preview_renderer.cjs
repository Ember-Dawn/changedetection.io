const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const src = fs.readFileSync(path.join(__dirname, '../../changedetectionio/static/js/notifications.js'), 'utf8');
const utilities = src.slice(0, src.indexOf('function setupNotificationTemplateLibrary()'));
function element(tag) {
  return {tag, children:[], style:{}, appendChild(node){this.children.push(node);}, replaceChildren(){this.children=[];}};
}
const context = {
  document: {createElement: element, createTextNode: value=>({text:String(value)})},
  window: {location:{origin:'https://example.org'}}, URL, Set, Array, JSON
};
vm.createContext(context);
vm.runInContext(utilities, context);
const flatten = node => node.text !== undefined ? node.text : (node.children || []).map(flatten).join('');
const parent = element('root');
context.notificationPreviewRender(parent, 'Previous: 178 ➜ 179', 'text');
assert.equal(flatten(parent), 'Previous: 178 ➜ 179');
context.notificationPreviewRender(parent, '*Bold* and escaped \\*star\\*', 'telegram_markdownv2');
assert.equal(parent.children.find(x=>x.tag).tag, 'b');
assert.equal(flatten(parent), 'Bold and escaped *star*');
const rich = JSON.stringify({blocks:[{type:'heading',text:{type:'url', text:'RTX 5080',url:'https://example.org/product'}}, {type:'details',summary:'More',blocks:[{type:'paragraph',text:'Current: $1200'}]}]});
assert.equal(context.notificationPreviewRender(parent,rich,'telegram_rich').length,0);
assert.equal(parent.children[0].tag,'strong');
assert.equal(parent.children[0].children[0].href,'https://example.org/product');
assert.equal(parent.children[1].tag,'details');
assert.equal(flatten(parent),'RTX 5080MoreCurrent: $1200');
assert.equal(context.notificationPreviewSafeUrl('javascript:alert(1)'),null);
assert.equal(context.notificationPreviewSafeUrl('data:text/html,test'),null);
assert.ok(context.notificationPreviewRender(parent,JSON.stringify({blocks:[{type:'unknown',text:'hello'}]}),'telegram_rich').includes('unknown'));
assert.throws(()=>context.notificationPreviewRender(parent,'not-json','telegram_rich'),SyntaxError);
console.log('Notification preview renderer: 8 assertions passed');
