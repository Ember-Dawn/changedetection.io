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
  const summaryEl = $('product-rule-summary');
  const summaryGrid = $('product-rule-summary-grid');
  const rawDetails = $('product-rule-raw-details');
  const diagnosticsEl = $('product-rule-diagnostics');
  const visual = $('product-rule-visual');
  const screenshot = $('product-rule-image');
  const screenshotLink = $('product-rule-image-link');
  const editorToggle = $('product-rule-editor-toggle');
  let rawResult = '';
  let resultData = null;
  let rulesIndex = [];
  const revisions = new Map();
  const fields = [
    ['price','Price'], ['currency','Currency'], ['in_stock','In stock'],
    ['pickup','Pickup'], ['shipping','Shipping'], ['stock_quantity','Quantity'],
    ['title','Title'], ['sku','SKU'],
  ];
  function clearPreview() {
    summaryEl.hidden = true;
    rawDetails.hidden = true;
    visual.hidden = true;
    diagnosticsEl.replaceChildren();
    summaryGrid.replaceChildren();
    screenshot.removeAttribute('src');
    screenshotLink.removeAttribute('href');
    rawResult = '';
    resultData = null;
    $('product-rule-copy-summary').disabled = true;
    $('product-rule-copy-json').disabled = true;
  }
  function showPreview(data) {
    clearPreview();
    if (!data || !data.dry_run || !data.result) return;
    const result = data.result;
    let found = 0;
    for (const [key,label] of fields) {
      const value = result[key];
      if (value !== undefined && value !== null) found++;
      const item = document.createElement('div'); item.className = 'px-summary-item';
      const name = document.createElement('span');name.textContent = label;
      const content = document.createElement('strong');
      content.textContent = value === true ? 'Yes' : value === false ? 'No' : value === undefined || value === null ? 'Unknown / N/A' : String(value);
      if (value === null || value === undefined) content.classList.add('px-unavailable');
      item.append(name,content);summaryGrid.append(item);
    }
    $('product-rule-summary-status').textContent = `${found}/${fields.length} values extracted · not verified`;
    summaryEl.hidden = false;
    for (const [key, detail] of Object.entries(data.details || {})) {
      const row = document.createElement('div');row.className = 'px-diagnostic-item';
      const name = document.createElement('strong');name.textContent = key;
      const value = document.createElement('span');
      value.textContent = detail.condition ? `Condition: ${detail.condition}; result: ${detail.value === null ? 'unknown' : String(detail.value)}` :
        `Matches: ${detail.matches}; source: ${(detail.selector && detail.selector.type) || 'none'}; raw: ${(detail.values || []).join(', ')}`;
      row.append(name,value); diagnosticsEl.append(row);
    }
    rawDetails.hidden = false;
    if (typeof data.screenshot === 'string' && /^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(data.screenshot)) {
      screenshot.src = data.screenshot;
      screenshotLink.href = data.screenshot;
      visual.hidden = false;
    }
  }

  let cleanText = '';
  let pending = false;
  let documentGeneration = 0;

  function message(value, kind = 'neutral', details = null) {
    statusEl.textContent = String(value);
    statusEl.dataset.kind = kind;
    if (details === null) {
      outputEl.textContent = '';
      outputEl.hidden = true;
      clearPreview();
      copyButton.disabled = true;
    } else {
      // Do not copy the potentially sensitive page screenshot into the raw JSON text.
      const publicResult = details && typeof details === 'object' ? {...details, screenshot: undefined} : details;
      rawResult = typeof publicResult === 'string' ? publicResult : JSON.stringify(publicResult, null, 2);
      outputEl.textContent = rawResult;
      showPreview(details);
      // showPreview clears stale previous data; publish the new copies afterwards.
      resultData = publicResult && typeof publicResult === 'object' ? publicResult.result : null;
      $('product-rule-copy-summary').disabled = !resultData;
      $('product-rule-copy-json').disabled = false;
      rawResult = typeof publicResult === 'string' ? publicResult : JSON.stringify(publicResult, null, 2);
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
    for (const element of [selector, saveButton, testButton, $('product-rule-new'), $('product-rule-import-trigger'), $('product-rule-duplicate'), $('product-rule-delete')]) element.disabled = isBusy;
    if (!isBusy) $('product-rule-delete').disabled = !selector.dataset.currentId;
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
  function setSelected(value) {
    selector.value = value;
    if (window.CDSelect) window.CDSelect.sync(selector);
  }
  async function refreshRules(selectedId) {
    const listing = await request('api/list');
    rulesIndex = listing.rules || [];
    revisions.clear();
    for (const rule of rulesIndex) revisions.set(rule.id, rule.revision);
    selector.replaceChildren(new Option('New rule / import JSON', ''));
    for (const rule of listing.rules || []) selector.add(new Option(labelFor(rule), rule.id));
    setSelected(selectedId || '');
    countEl.textContent = `${(listing.rules || []).length} saved`;
    $('product-rule-delete').disabled = !selector.value;
  }

  editor.addEventListener('input', updateDirty);
  editorToggle.addEventListener('click', () => {
    const expanded = editor.classList.toggle('px-editor-expanded');
    editorToggle.setAttribute('aria-expanded',String(expanded));
    editorToggle.textContent = expanded ? 'Collapse editor' : 'Expand editor';
  });
  $('product-rule-new').addEventListener('click', () => {
    if (pending || !confirmOverwrite()) return;
    setSelected('');
    selector.dataset.currentId = '';
    $('product-rule-delete').disabled = true;
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
      if (!confirmOverwrite()) { setSelected(selector.dataset.currentId || ''); return; }
      selector.dataset.currentId = '';
      $('product-rule-delete').disabled = true;
      fileInput.value = '';
      filenameEl.textContent = 'No file selected';
      editText('', {saved: true});
      message('Ready for a new rule.');
      return;
    }
    if (!confirmOverwrite()) { setSelected(selector.dataset.currentId || ''); return; }
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
      $('product-rule-delete').disabled = false;
      message(`Loaded ${id}.`, 'success');
    } catch (err) {
      setSelected(selector.dataset.currentId || '');
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
      setSelected('');
      selector.dataset.currentId = '';
      $('product-rule-delete').disabled = true;
      editText(text);
      filenameEl.textContent = `Imported: ${file.name}`;
      const imported = JSON.parse(text);
      const same = rulesIndex.find(r => r.id === imported.id);
      message(same ? `Rule ID ${imported.id} already exists. Test first; saving changes requires explicit overwrite confirmation.` : 'Imported locally. Validate and test before saving.', 'success');
    } catch (err) { message(`Import failed: ${err.message}`, 'error'); }
    finally { lock(false); fileInput.value = ''; }
  });
  function overlapWarning(rule) {
    const domains = (rule.match && rule.match.domains) || [];
    const other = rulesIndex.filter(item => item.id !== rule.id && item.enabled &&
      item.domains.some(domain => domains.some(candidate => domain === candidate || domain.endsWith('.'+candidate) || candidate.endsWith('.'+domain))));
    return other.length ? `\nWarning: overlapping domain rules (${other.map(r => r.id).join(', ')}). Auto-mode Watches may need an explicit rule selection.` : '';
  }
  saveButton.addEventListener('click', async () => {
    if (pending) return;
    let payload;
    try { payload = read(); } catch (err) { message(err.message, 'error'); return; }
    const existing = rulesIndex.find(rule => rule.id === payload.id);
    const currentId = selector.dataset.currentId || '';
    const isSame = existing && currentId === payload.id && !updateDirty();
    if (isSame) { message('Identical saved rule; nothing to update.', 'success'); return; }
    if (existing && !window.confirm(`Rule ID "${payload.id}" already exists. Overwrite its JSON?\nThis affects Watches that use the rule.${overlapWarning(payload)}`)) return;
    const submittedText = editor.value;
    const expectedGeneration = documentGeneration;
    lock(true);
    message('Validating and saving rule…', 'busy');
    try {
      const response = await request('api/save', {
        rule:payload, expected_signature:existing ? revisions.get(payload.id) : null,
        overwrite:Boolean(existing),
      });
      await refreshRules(response.rule.id);
      selector.dataset.currentId = response.rule.id;
      filenameEl.textContent = `Saved rule: ${response.rule.id}`;
      if (expectedGeneration === documentGeneration && editor.value === submittedText) {
        cleanText = submittedText;
        updateDirty();
      }
      message(`${response.status === 'unchanged' ? 'Unchanged' : response.status === 'updated' ? 'Updated' : 'Created'} ${response.rule.id}.${overlapWarning(response.rule)}`, 'success');
    } catch (err) { message(`Save failed: ${err.message}`, 'error'); }
    finally { lock(false); }
  });
  $('product-rule-duplicate').addEventListener('click', () => {
    if (pending) return;
    let source;
    try { source = read(); } catch (err) { message(err.message,'error'); return; }
    const original = String(source.id || 'new-rule').slice(0,48);
    let id = `${original}-copy`, i = 2;
    while (rulesIndex.some(r => r.id === id)) id = `${original}-copy${i++}`;
    source.id = id;
    source.name = String(source.name || id).slice(0,90) + ' copy';
    setSelected('');selector.dataset.currentId = '';
    editText(JSON.stringify(source,null,2));
    filenameEl.textContent = `Unsaved copy: ${id}`;
    message('Rule duplicated locally. Save to create the new ID.', 'success');
    $('product-rule-delete').disabled = true;
  });
  $('product-rule-delete').addEventListener('click', async () => {
    const rid = selector.dataset.currentId;
    if (pending || !rid || !confirmOverwrite()) return;
    lock(true);
    try {
      const {references} = await request('api/' + encodeURIComponent(rid) + '/references');
      if (references.length) {
        const titles = references.slice(0,5).map(w => w.title).join(', ');
        message(`Cannot delete ${rid}: referenced by ${references.length} Watches (${titles}). Unbind them first.`, 'error');
        return;
      }
      if (!window.confirm(`Delete rule ${rid} from the Git-tracked rules directory? This cannot be undone outside Git.`)) return;
      await request('api/' + encodeURIComponent(rid) + '/delete', {expected_signature:revisions.get(rid)});
      await refreshRules('');
      selector.dataset.currentId = '';
      editText('',{saved:true});
      filenameEl.textContent='Rule deleted';
      message(`Deleted ${rid}. Git will record the deletion.`, 'success');
    } catch (err) { message(`Delete failed: ${err.message}`, 'error'); }
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
    const text = rawResult || outputEl.textContent;
    try {
      await navigator.clipboard.writeText(text);
      statusEl.textContent = 'Result copied to clipboard.';
    } catch (_) {
      message('Clipboard unavailable; select and copy the results manually.', 'error', text);
    }
  });
  async function copyText(text) {
    if (!text) return;
    try { await navigator.clipboard.writeText(text); statusEl.textContent='Copied to clipboard.'; }
    catch (_) { statusEl.textContent='Clipboard unavailable; select the JSON and copy manually.'; }
  }
  $('product-rule-copy-summary').addEventListener('click', () => copyText(resultData ? JSON.stringify(resultData,null,2) : ''));
  $('product-rule-copy-json').addEventListener('click', () => copyText(rawResult));
  window.addEventListener('beforeunload', (event) => {
    if (editor.value === cleanText) return;
    event.preventDefault();
    event.returnValue = '';
  });
  updateDirty();
})();
