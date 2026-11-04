"""Settings for condition-driven product purchase notifications."""
from wtforms import validators, FloatField
from wtforms.fields.choices import RadioField, SelectField
from wtforms import Form, FormField
from flask_babel import lazy_gettext as _l
from changedetectionio.forms import processor_text_json_diff_form


class RestockSettingsForm(Form):
    alert_mode = RadioField(_l('Product alert goal'), choices=[
        ('stock_and_price', _l('In stock AND price below target')),
        ('stock_only', _l('In stock only')),
        ('price_only', _l('Price below target (ignore stock)')),
    ], default='stock_only')
    target_price = FloatField(_l('Target price (strictly below)'), validators=[
        validators.Optional(), validators.NumberRange(min=0),
    ], render_kw={'placeholder': 'e.g. 1300', 'min': '0', 'step': 'any'})
    extraction_mode = RadioField(_l('Product extraction mode'), choices=[
        ('auto', _l('Auto: matching custom rule, otherwise built-in')),
        ('rule', _l('Selected rule only (error on failure)')),
        ('builtin', _l('Built-in metadata and plugins only')),
    ], default='auto')
    extraction_rule_id = SelectField(_l('Selected rule'),
        choices=[('', _l('Select rule'))], validate_choice=False)

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        if self.alert_mode.data in ('stock_and_price', 'price_only') and self.target_price.data is None:
            self.target_price.errors.append(_l('A target price is required for this monitoring goal.'))
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
        return _l('Product purchase alerts')

    def extra_form_content(self):
        output = ''
        if getattr(self, 'watch', None) and getattr(self, 'datastore', None):
            for tag_uuid in self.watch.get('tags', []):
                tag = self.datastore.data['settings']['application']['tags'].get(tag_uuid, {})
                if tag.get('overrides_watch'):
                    output += '<p><strong>Note: A Group tag overrides product alert settings on this Watch.</strong></p>'
                    break

        output += r"""
        {% from '_helpers.html' import render_field %}
        <style>
          #purchase-alert-settings .purchase-radio ul {list-style:none!important; margin:8px 0!important; padding:0!important}
          #purchase-alert-settings .purchase-radio li {display:flex!important; align-items:center!important; gap:9px; margin:8px 0!important; padding:0!important; list-style:none!important}
          #purchase-alert-settings .purchase-radio li input[type=radio] {flex:0 0 auto; margin:0!important; width:16px; height:16px}
          #purchase-alert-settings .purchase-radio li label {display:inline!important; width:auto!important; margin:0!important; padding:0!important; line-height:1.5; cursor:pointer}
          #purchase-alert-settings .purchase-rule-select {max-width:520px; min-width:260px; width:100%;}
          #purchase-alert-settings .purchase-rule-select select {width:100%; max-width:100%;}
          #purchase-alert-settings .purchase-note {display:block; color:#8394ab; max-width:720px; margin:7px 0 14px; line-height:1.55}
          #purchase-target-price[hidden] {display:none!important}
          #purchase-alert-settings .purchase-price {margin:14px 0;}
          #purchase-alert-settings .purchase-price input {max-width:240px;}
        </style>
        <fieldset id="purchase-alert-settings">
          <fieldset class="pure-group purchase-radio">
            {{ render_field(form.processor_config_restock_diff.alert_mode) }}
            <span class="purchase-note">The first valid check establishes a baseline. When qualified, every price change (up or down) triggers a new alert; unchanged price does not.</span>
          </fieldset>
          <fieldset id="purchase-target-price" class="pure-group purchase-price">
            {{ render_field(form.processor_config_restock_diff.target_price) }}
            <span class="purchase-note">Strictly below the target, not equal. Stock-and-price requires both conditions; price-only ignores stock.</span>
          </fieldset>
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
            function syncPurchaseMode(){
              const radio = document.querySelector('input[name="processor_config_restock_diff-alert_mode"]:checked');
              const group = document.getElementById('purchase-target-price');
              if(group) group.hidden = !!radio && radio.value === 'stock_only';
            }
            document.addEventListener('change', function(event){
              if(event.target.name === 'processor_config_restock_diff-alert_mode') syncPurchaseMode();
            });
            if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', syncPurchaseMode);
            else syncPurchaseMode();
          })();
        </script>
        """
        return output
