'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const css = fs.readFileSync(path.join(root, 'changedetectionio/blueprint/quick_verify/static/quick-verify.css'), 'utf8');
const html = fs.readFileSync(path.join(root, 'changedetectionio/blueprint/quick_verify/templates/quick-verify.html'), 'utf8');

test('two separate rows keep the original remote controls and actions', () => {
  const first = html.indexOf('class="qv-input-row"');
  const second = html.indexOf('class="qv-bottom-row"');
  assert.ok(first > 0 && second > first);
  for (const id of ['qv-text','qv-send','qv-enter','qv-scroll-up','qv-scroll-down']) {
    assert.ok(html.indexOf('id="' + id + '"', first) < second && html.indexOf('id="' + id + '"', first) >= first, id);
  }
  for (const id of ['qv-back','qv-reload','qv-fit','qv-finish','qv-close']) {
    assert.ok(html.indexOf('id="' + id + '"', second) > second, id);
  }
  assert.doesNotMatch(html, /id="qv-scroll-mode"/);
});

test('square icons and input/session buttons share responsive height variable', () => {
  assert.match(css, /--qv-size:\s*40px/);
  assert.match(css, /--qv-size:\s*38px/);
  assert.match(css, /--qv-size:\s*34px/);
  assert.match(css, /\.qv-input-row button,\s*\.qv-bottom-row \.qv-tools button\s*\{[^}]*width:\s*var\(--qv-size\);[^}]*height:\s*var\(--qv-size\)/s);
  assert.match(css, /\.qv-input-row input\s*\{[^}]*height:\s*var\(--qv-size\)/s);
  assert.match(css, /\.qv-bottom-row \.qv-primary button\s*\{[^}]*height:\s*var\(--qv-size\)/s);
});

test('remote screen alone blocks native touch and image menus', () => {
  assert.match(css, /\.qv-screen\s*\{[^}]*touch-action:\s*none/s);
  assert.match(css, /\.qv-screen img\s*\{[^}]*pointer-events:\s*none/s);
  assert.doesNotMatch(css, /(^|,)\s*(?:body|html|input)\s*\{[^}]*-webkit-touch-callout:\s*none/m);
});
