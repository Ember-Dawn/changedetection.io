/* Product Extractors UI, vanilla JS; API and original control IDs unchanged. */
(() => {
  'use strict';
  const root = document.getElementById('px-root');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const base = root.dataset.apiBase;
  const csrf = root.dataset.csrf;
  const editor = $('product-rule-json');
  const selector = $('product-rule-list');
  const fileInput = $('product-rule-import');
  const saveButton = $('product-rule-save');
  const testButton = $('product-rule-test');
  const copyButton = $('product-rule-copy-result');
  const statusEl = $('product-rule-message');
  const outputEl = $('product-rule-result');
  const filenameEl = $('product-rule-filename');
  const dirtyEl = $('product-rule-dirty');
  const countEl = $('px-rule-count');
  let cleanText = '';
  let pending = false;
  let documentGeneration = 0;

  function message(value, kind = 'neutral', details = null) {
    statusEl.textContent = String(value);
    statusEl.dataset.kind = kind;
    if (details === null) {
      outputEl.textContent = '';
      outputEl.hidden = true;
      copyButton.disabled = true;
    } else {
      outputEl.textContent = typeof details === 'string' ? details : JSON.stringify(details, null, 2);
      outputEl.hidden = false;
      copyButton.disabled = false;
    }
  }
  function updateDirty() {
    const dirty = editor.value !== cleanText;
    dirtyEl.textContent = dirty ? 'Unsaved changes' : 'No changes';
    dirtyEl.dataset.dirty = String(dirty);
    return dirty;
  }
  function editText(text, {saved = false} = {}) {
    editor.value = text;
    cleanText = saved ? text : '';
    documentGeneration++;
    updateDirty();
  }
  function confirmOverwrite() {
    return !updateDirty() || window.confirm('Discard unsaved changes to this rule?');
  }
  function lock(isBusy) {
    pending = isBusy;
    for (const element of [selector, saveButton, testButton, $('product-rule-new'), $('product-rule-import-trigger')]) element.disabled = isBusy;
  }
  async function request(path, data) {
    const response = await fetch(base + path, {
      method: data === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      ...(data === undefined ? {} : {body: JSON.stringify(data)}),
    });
    let value;
    try { value = await response.json(); }
    catch (_) { throw new Error(`HTTP ${response.status}: invalid server response`); }
    if (!response.ok) throw new Error((value && value.error) || `HTTP ${response.status}`);
    return value;
  }
  function read() {
    try { return JSON.parse(editor.value); }
    catch (err) { throw new Error(`Invalid JSON: ${err.message}`); }
  }
  function labelFor(rule) { return `${rule.name} — ${rule.id}${rule.enabled ? '' : ' (disabled)'}`; }
  async function refreshRules(selectedId) {
    const listing = await request('api/list');
    selector.replaceChildren(new Option('New rule / import JSON', ''));
    for (const rule of listing.rules || []) selector.add(new Option(labelFor(rule), rule.id));
    selector.value = selectedId || '';
    countEl.textContent = `${(listing.rules || []).length} saved`;
  }

  editor.addEventListener('input', updateDirty);
  $('product-rule-new').addEventListener('click', () => {
    if (pending || !confirmOverwrite()) return;
    selector.value = '';
    fileInput.value = '';
    filenameEl.textContent = 'New unsaved rule';
    editText('', {saved: true});
    message('Create a new JSON rule or import one from a file.');
    editor.focus();
  });
  selector.addEventListener('change', async () => {
    if (pending) return;
    const id = selector.value;
    if (!id) {
      if (!confirmOverwrite()) { selector.value = selector.dataset.currentId || ''; return; }
      selector.dataset.currentId = '';
      fileInput.value = '';
      filenameEl.textContent = 'No file selected';
      editText('', {saved: true});
      message('Ready for a new rule.');
      return;
    }
    if (!confirmOverwrite()) { selector.value = selector.dataset.currentId || ''; return; }
    const expectedGeneration = documentGeneration;
    lock(true);
    message(`Loading ${id}…`, 'busy');
    try {
      const rule = await request('api/' + encodeURIComponent(id));
      if (expectedGeneration !== documentGeneration) return;
      const text = JSON.stringify(rule, null, 2);
      editText(text, {saved: true});
      filenameEl.textContent = `Loaded rule: ${id}`;
      selector.dataset.currentId = id;
      message(`Loaded ${id}.`, 'success');
    } catch (err) {
      selector.value = selector.dataset.currentId || '';
      message(`Load failed: ${err.message}`, 'error');
    } finally { lock(false); }
  });
  $('product-rule-import-trigger').addEventListener('click', () => {
    if (!pending && confirmOverwrite()) fileInput.click();
  });
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    if (file.size > 131072) { message('JSON rule exceeds the 128 KB size limit.', 'error'); fileInput.value = ''; return; }
    const expectedGeneration = documentGeneration;
    lock(true);
    try {
      const text = await file.text();
      if (expectedGeneration !== documentGeneration) return;
      JSON.parse(text); // Give immediate feedback for invalid imported JSON.
      selector.value = '';
      selector.dataset.currentId = '';
      editText(text);
      filenameEl.textContent = `Imported: ${file.name}`;
      message('Imported locally. Validate and test before saving.', 'success');
    } catch (err) { message(`Import failed: ${err.message}`, 'error'); }
    finally { lock(false); fileInput.value = ''; }
  });
  saveButton.addEventListener('click', async () => {
    if (pending) return;
    let payload;
    try { payload = read(); } catch (err) { message(err.message, 'error'); return; }
    const submittedText = editor.value;
    const expectedGeneration = documentGeneration;
    lock(true);
    message('Validating and saving rule…', 'busy');
    try {
      const response = await request('api/save', payload);
      await refreshRules(response.rule.id);
      selector.dataset.currentId = response.rule.id;
      filenameEl.textContent = `Saved rule: ${response.rule.id}`;
      if (expectedGeneration === documentGeneration && editor.value === submittedText) {
        cleanText = submittedText;
        updateDirty();
      }
      message(`Saved ${response.rule.id} to extractor-rules/rules/.`, 'success');
    } catch (err) { message(`Save failed: ${err.message}`, 'error'); }
    finally { lock(false); }
  });
  testButton.addEventListener('click', async () => {
    if (pending) return;
    let payload;
    try {
      payload = {
        rule: read(),
        url: $('product-rule-url').value.trim(),
        fetch_backend: $('product-rule-backend').value,
      };
      const html = $('product-rule-html').value;
      if (html) payload.html = html;
    } catch (err) { message(err.message, 'error'); return; }
    lock(true);
    message('Extracting product data…', 'busy');
    try { message('Dry run completed.', 'success', await request('api/test', payload)); }
    catch (err) { message(`Test failed: ${err.message}`, 'error'); }
    finally { lock(false); }
  });
  copyButton.addEventListener('click', async () => {
    if (copyButton.disabled) return;
    const text = outputEl.textContent;
    try {
      await navigator.clipboard.writeText(text);
      statusEl.textContent = 'Result copied to clipboard.';
    } catch (_) {
      message('Clipboard unavailable; select and copy the results manually.', 'error', text);
    }
  });
  window.addEventListener('beforeunload', (event) => {
    if (editor.value === cleanText) return;
    event.preventDefault();
    event.returnValue = '';
  });
  updateDirty();
})();
