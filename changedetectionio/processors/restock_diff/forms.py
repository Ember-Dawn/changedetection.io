"""Settings for stock and price event monitoring."""
from pathlib import Path
from html import escape
from wtforms import validators, FloatField, BooleanField
from wtforms.fields.choices import RadioField, SelectField
from wtforms import Form, FormField
from flask_babel import lazy_gettext as _l
from changedetectionio.forms import processor_text_json_diff_form


class RestockSettingsForm(Form):
    price_mode = RadioField(_l('1. Price monitoring'), choices=[
        ('none', _l('Do not monitor price')),
        ('below', _l('Below a target price')),
        ('above', _l('Above a target price')),
        ('any_change', _l('Any price change')),
        ('percent_down', _l('Cumulative price decrease (%)')),
        ('percent_up', _l('Cumulative price increase (%)')),
        ('percent_any', _l('Cumulative price change in either direction (%)')),
    ], default='none')
    price_threshold = FloatField(_l('Price / percentage threshold'), validators=[
        validators.Optional(), validators.NumberRange(min=0),
    ], render_kw={'placeholder': 'e.g. 1300 or 10', 'min': '0', 'step': 'any'})
    price_follow_changes = BooleanField(_l('Continue alerting on price changes while target is met'), default=True)
    stock_mode = RadioField(_l('2. Stock monitoring'), choices=[
        ('none', _l('Do not monitor stock')),
        ('in_stock', _l('Currently in stock (price filter)')),
        ('out_of_stock', _l('Currently out of stock (price filter)')),
        ('restock', _l('Back in stock')),
        ('sold_out', _l('Sold out')),
        ('any_change', _l('Any stock status change')),
    ], default='restock')
    combine_mode = RadioField(_l('3. Combine stock and price'), choices=[
        ('and', _l('AND — both conditions must match (default)')),
        ('or', _l('OR — either condition may trigger')),
    ], default='and')
    extraction_mode = RadioField(_l('Product extraction mode'), choices=[
        ('rule', _l('Selected rule only (error on failure)')),
        ('builtin', _l('Built-in metadata and plugins only')),
    ], default='rule')
    extraction_rule_id = SelectField(_l('Selected rule'),
        choices=[('', _l('Select rule'))], validate_choice=False)

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        from .purchase_alert import normalize_settings, PurchaseAlertConfigurationError
        try:
            normalize_settings({
                'price_mode': self.price_mode.data,
                'stock_mode': self.stock_mode.data,
                'combine_mode': self.combine_mode.data,
                'price_threshold': self.price_threshold.data,
                'price_follow_changes': bool(self.price_follow_changes.data),
            })
        except PurchaseAlertConfigurationError as exc:
            self.price_mode.errors.append(str(exc))
            valid = False
        if self.extraction_mode.data == 'rule' and not self.extraction_rule_id.data:
            self.extraction_rule_id.errors.append('Select a product extraction rule or choose Built-in.')
            valid = False
        if self.extraction_mode.data == 'auto':
            self.extraction_mode.errors.append('Legacy Auto mode: select a specific rule or Built-in before saving.')
            valid = False
        return valid


class processor_settings_form(processor_text_json_diff_form):
    processor_config_restock_diff = FormField(RestockSettingsForm)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from changedetectionio.product_extraction import list_rules
        try:
            self.processor_config_restock_diff.form.extraction_rule_id.choices = (
                [('', _l('Select rule'))] +
                [(r['id'], '{} — {}'.format(r['name'], r['id'])) for r in list_rules()]
            )
        except OSError:
            pass

    def extra_tab_content(self):
        return _l('Stock & Price alerts')

    def extra_form_content(self):
        output = ''
        if getattr(self, 'watch', None) and getattr(self, 'datastore', None):
            for tag_uuid in self.watch.get('tags', []):
                tag = self.datastore.data['settings']['application']['tags'].get(tag_uuid, {})
                if tag.get('overrides_watch'):
                    output += '<p><strong>Note: A Group tag overrides product alert settings on this Watch.</strong></p>'
                    break

        # The same Markdown source is used by the WebUI's copy action and AI handoff.
        docs_path = Path(__file__).resolve().parents[3] / 'docs/product-extraction/STOCK_PRICE_RULES.md'
        documentation = escape(docs_path.read_text(encoding='utf-8'))
        output += r"""
        {% from '_helpers.html' import render_field %}
        <style>
          #purchase-alert-settings .purchase-radio ul {list-style:none!important; margin:8px 0!important; padding:0!important}
          #purchase-alert-settings .purchase-radio li {display:flex!important; align-items:center!important; gap:9px; margin:8px 0!important; padding:0!important; list-style:none!important}
          #purchase-alert-settings .purchase-radio li input[type=radio] {flex:0 0 auto; margin:0!important; width:16px; height:16px}
          #purchase-alert-settings .purchase-radio li label {display:inline!important; width:auto!important; margin:0!important; padding:0!important; line-height:1.5; cursor:pointer}
          #purchase-alert-settings .purchase-rule-select {max-width:520px; min-width:260px; width:100%}
          #purchase-alert-settings .purchase-rule-select select {width:100%;max-width:100%}
          #purchase-alert-settings .purchase-note {display:block; color:#8394ab; max-width:720px; margin:7px 0 14px; line-height:1.55}
          #purchase-alert-settings .purchase-price {margin:14px 0}
          #purchase-alert-settings .purchase-price input {max-width:240px}
          #purchase-alert-settings [hidden] {display:none!important}
          #purchase-alert-settings .purchase-doc {max-width:800px; margin:15px 0}
          #purchase-alert-settings .purchase-doc summary {cursor:pointer; font-weight:600; padding:8px 0}
          #purchase-alert-settings .purchase-doc pre {white-space:pre-wrap; word-break:break-word; max-height:340px; overflow:auto; font-size:12px; padding:12px; border:1px solid #8394ab55; border-radius:6px}
        </style>
        <fieldset id="purchase-alert-settings">
          <fieldset class="pure-group purchase-radio">
            {{ render_field(form.processor_config_restock_diff.price_mode) }}
          </fieldset>
          <fieldset id="purchase-price-threshold" class="pure-group purchase-price">
            {{ render_field(form.processor_config_restock_diff.price_threshold) }}
            <span class="purchase-note">Prices use strict thresholds. Percentages use a cumulative anchor since the last qualifying percentage alert (positive; decreases at most 100%).</span>
          </fieldset>
          <fieldset id="purchase-follow-changes" class="pure-group">
            {{ render_field(form.processor_config_restock_diff.price_follow_changes) }}
            <span class="purchase-note">Enabled by default: continue notifying of either price direction while the target remains satisfied.</span>
          </fieldset>
          <fieldset class="pure-group purchase-radio">
            {{ render_field(form.processor_config_restock_diff.stock_mode) }}
            <span id="purchase-stock-note" class="purchase-note">Current stock filters are available only while price monitoring is on.</span>
          </fieldset>
          <fieldset id="purchase-combine-mode" class="pure-group purchase-radio">
            {{ render_field(form.processor_config_restock_diff.combine_mode) }}
            <span class="purchase-note">AND is the default. For a stock event plus a fixed price threshold, AND requires the stock event and the current price to meet the threshold.</span>
          </fieldset>
          <details class="purchase-doc">
            <summary>Monitoring rules — expand / copy Markdown for AI</summary>
            <button type="button" class="pure-button" id="purchase-copy-rules">Copy Markdown</button>
            <span id="purchase-copy-status" role="status" aria-live="polite"></span>
            <pre id="purchase-rules-markdown">__RULES_MARKDOWN__</pre>
          </details>
          <fieldset class="pure-group purchase-radio">
            {{ render_field(form.processor_config_restock_diff.extraction_mode) }}
          </fieldset>
          <fieldset class="pure-group purchase-rule-select">
            {{ render_field(form.processor_config_restock_diff.extraction_rule_id, **{'data-custom-select': ''}) }}
            <span class="purchase-note">Manage, import and test extraction rules in <a href="/product-extractors/" target="_blank" rel="noopener">Product Extractors</a>.</span>
          </fieldset>
        </fieldset>
        <script>
          (function(){
            const prefix = 'processor_config_restock_diff-';
            function selected(name) {
              const active = document.querySelector('input[name="' + prefix + name + '"]:checked');
              return active ? active.value : 'none';
            }
            function syncPurchaseMode() {
              const root = document.getElementById('purchase-alert-settings');
              if (!root) return;
              const price = selected('price_mode');
              const stock = selected('stock_mode');
              const enabled = price !== 'none';
              root.querySelector('#purchase-price-threshold').hidden = ['none', 'any_change'].includes(price);
              root.querySelector('#purchase-follow-changes').hidden = !['below','above'].includes(price);
              root.querySelectorAll('input[name="'+prefix+'stock_mode"]').forEach(input => {
                const isFilter = ['in_stock','out_of_stock'].includes(input.value);
                const row = input.closest('li');
                if (row && isFilter) row.hidden = !enabled;
                input.disabled = isFilter && !enabled;
              });
              if (!enabled && ['in_stock','out_of_stock'].includes(stock)) {
                const alternative = root.querySelector('input[name="'+prefix+'stock_mode"][value="none"]');
                if (alternative) alternative.checked = true;
              }
              const currentStock = selected('stock_mode');
              if (['in_stock','out_of_stock'].includes(currentStock)) {
                const andMode = root.querySelector('input[name="'+prefix+'combine_mode"][value="and"]');
                if (andMode) andMode.checked = true;
              }
              root.querySelector('#purchase-combine-mode').hidden = !enabled || !['restock','sold_out','any_change'].includes(currentStock);
              const threshold = root.querySelector('input[name="'+prefix+'price_threshold"]');
              if (threshold) threshold.required = !['none','any_change'].includes(price);
            }
            const ruleSelect = document.querySelector('select[name="'+prefix+'extraction_rule_id"]');
            const urlInput = document.querySelector('input[name="url"]');
            const ruleRadio = document.querySelector('input[name="'+prefix+'extraction_mode"][value="rule"]');
            const modeInputs = document.querySelectorAll('input[name="'+prefix+'extraction_mode"]');
            let autoMatched = false;
            let applyingAutomaticSelection = false;
            let manualRule = Boolean(ruleSelect && ruleSelect.value) ||
                Array.from(modeInputs).some(input => input.checked && input.value !== 'rule');
            let latestRequest = 0;
            const hint = document.createElement('span');
            hint.className = 'purchase-note';
            hint.setAttribute('role', 'status');
            if (ruleSelect) {
              ruleSelect.closest('fieldset').appendChild(hint);
              ruleSelect.addEventListener('change', () => {
                if (applyingAutomaticSelection) return;
                manualRule = Boolean(ruleSelect.value); autoMatched = false; hint.textContent = '';
              });
            }
            modeInputs.forEach(input => input.addEventListener('change', () => { manualRule = true; autoMatched = false; }));
            async function matchRule() {
              if (!urlInput || !ruleSelect || !window.productRuleMatchURL) return;
              const requestId = ++latestRequest;
              const url = urlInput.value.trim();
              if (!url || !/^https?:\/\//i.test(url)) return;
              try {
                const response = await fetch(window.productRuleMatchURL + '?url=' + encodeURIComponent(url), {credentials:'same-origin'});
                if (!response.ok) return;
                const data = await response.json();
                if (requestId !== latestRequest) return;
                if (manualRule && !autoMatched) {
                  const match = data.matches.find(item => item.id === ruleSelect.value);
                  hint.textContent = match ? 'Selected rule matches this URL.' :
                    (data.matches.length === 1 ? 'URL matches ' + data.matches[0].name + '; current selection kept.' :
                    data.matches.length ? 'Multiple rules match this URL; current selection kept.' :
                    'No matching rule for this URL; current selection kept.');
                  return;
                }
                if (data.matches.length === 1) {
                  applyingAutomaticSelection = true;
                  ruleSelect.value = data.matches[0].id;
                  ruleSelect.dispatchEvent(new Event('change', {bubbles:true}));
                  applyingAutomaticSelection = false;
                  manualRule = false;
                  autoMatched = true;
                  if (ruleRadio) ruleRadio.checked = true;
                  hint.textContent = 'Automatically matched by URL: ' + data.matches[0].name;
                } else {
                  if (autoMatched) {
                    ruleSelect.value = '';
                    if (window.CDSelect) window.CDSelect.sync(ruleSelect);
                  }
                  autoMatched = false;
                  hint.textContent = data.matches.length ? 'Multiple rules match this URL; select one manually.' : 'No matching rule; select a rule or Built-in.';
                }
              } catch (_) { hint.textContent = 'Rule matching unavailable; select manually.'; }
            }
            if (urlInput) {
              let matchTimer;
              urlInput.addEventListener('input', () => {
                clearTimeout(matchTimer);
                matchTimer = setTimeout(matchRule, 400);
              });
              urlInput.addEventListener('change', () => {
                clearTimeout(matchTimer);
                matchRule();
              });
            }
            // Do not rewrite existing Watch configuration on initial load.
            if (ruleSelect && !ruleSelect.value && !manualRule) matchRule();
            document.addEventListener('change', function(event) {
              if (event.target.name && event.target.name.startsWith(prefix)) syncPurchaseMode();
            });
            document.addEventListener('click', function(event) {
              if (event.target.id !== 'purchase-copy-rules') return;
              const rules = document.getElementById('purchase-rules-markdown').textContent;
              const status = document.getElementById('purchase-copy-status');
              const fallback = () => {
                const input = document.createElement('textarea');
                input.value = rules; input.style.position = 'fixed'; input.style.left = '-9999px';
                document.body.appendChild(input); input.select();
                const success = document.execCommand('copy'); input.remove();
                status.textContent = success ? 'Copied' : 'Copy failed; select and copy the text below.';
              };
              if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(rules).then(() => status.textContent = 'Copied', fallback);
              } else fallback();
            });
            if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', syncPurchaseMode);
            else syncPurchaseMode();
          })();
        </script>
        """.replace('__RULES_MARKDOWN__', documentation)
        return output
