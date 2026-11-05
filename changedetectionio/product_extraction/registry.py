"""Git-friendly, bind-mounted rule registry. JSON never executes user code."""
import copy
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from urllib.parse import urlsplit
from babel.core import get_global
from .models import RuleError

ID = re.compile(r'^[a-z][a-z0-9_-]{1,63}$')
ALLOWED_FIELDS = {'price','currency','in_stock','stock_quantity','title','sku','pickup','shipping'}
ALLOWED_SOURCES = {'css','xpath','jsonpath','regex'}
WRITE_LOCK = threading.RLock()
MAX_RULE_BYTES = 131072


def root():
    override = os.environ.get('PRODUCT_EXTRACTOR_RULES_DIR')
    if override:return Path(override).resolve()
    mounted = Path('/extractor-rules')
    return mounted.resolve() if mounted.is_dir() else Path(__file__).resolve().parents[2] / 'extractor-rules'


CONDITION_OPS = {'exists', 'contains', 'equals', 'ref', 'any', 'all', 'not', 'if', 'coalesce', 'literal'}
MAX_CONDITION_NODES = 64


def _validate_selector(selector, field):
    if not isinstance(selector, dict) or selector.get('type') not in ALLOWED_SOURCES:
        raise RuleError(f'{field}: unknown selector type')
    if set(selector) - {'type', 'value', 'selector', 'extract', 'attribute'}:
        raise RuleError(f'{field}: unsupported selector keys')
    value = selector.get('value') or selector.get('selector')
    if not isinstance(value, str) or not 1 <= len(value) <= 512:
        raise RuleError(f'{field}: invalid selector')
    if selector.get('extract', 'text') not in ('text', 'html', 'value', 'attr'):
        raise RuleError(f'{field}: invalid extract mode')
    if selector.get('extract') == 'attr' and not re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_:-]{0,70}', selector.get('attribute', '')):
        raise RuleError(f'{field}: invalid attribute')


def _validate_condition(expr, field, depth=0, budget=None):
    if budget is None:budget = [0]
    budget[0] += 1
    if budget[0] > MAX_CONDITION_NODES or depth > 8:
        raise RuleError(f'{field}: condition complexity limit exceeded')
    if not isinstance(expr, dict) or expr.get('op') not in CONDITION_OPS:
        raise RuleError(f'{field}: unsupported condition operator')
    op = expr['op']
    required = {'exists': {'selector'}, 'contains': {'selector', 'value'},
        'equals': {'selector', 'value'}, 'ref': {'field'}, 'any': {'items'},
        'all': {'items'}, 'not': {'item'}, 'if': {'test', 'then', 'else'},
        'coalesce': {'items'}, 'literal': {'value'}}[op]
    if set(expr) != required | {'op'} and not (op in ('exists', 'contains', 'equals') and set(expr) == required | {'op','guard'}):
        raise RuleError(f'{field}: unsupported condition parameters')
    if op in ('exists', 'contains', 'equals'):
        _validate_selector(expr['selector'], field)
        if 'guard' in expr:_validate_selector(expr['guard'], field)
        if op != 'exists' and (not isinstance(expr['value'], str) or len(expr['value']) > 200):
            raise RuleError(f'{field}: condition value must be a short string')
    elif op == 'ref':
        if (not isinstance(expr['field'],str) or
                expr['field'] not in {'pickup','shipping'} or field != 'in_stock'):
            raise RuleError(f'{field}: invalid condition field reference')
    elif op in ('any','all','coalesce'):
        items = expr['items']
        if not isinstance(items,list) or not 1 <= len(items) <= 12:
            raise RuleError(f'{field}: condition requires 1-12 items')
        for item in items:_validate_condition(item,field,depth+1,budget)
    elif op == 'not':_validate_condition(expr['item'],field,depth+1,budget)
    elif op == 'if':
        for key in ('test','then','else'):_validate_condition(expr[key],field,depth+1,budget)
    elif op == 'literal' and expr['value'] is not None and type(expr['value']) is not bool:
        raise RuleError(f'{field}: literal must be true, false or null')


def validate(rule):
    if not isinstance(rule, dict) or rule.get('schema_version') != 1:
        raise RuleError('Expected schema_version: 1')
    rid = rule.get('id')
    if not isinstance(rid, str) or not ID.fullmatch(rid):
        raise RuleError('Rule id must be 2-64 lowercase URL-safe characters')
    if not isinstance(rule.get('name'), str) or not 1 <= len(rule['name']) <= 100:
        raise RuleError('Rule name is required (max 100 characters)')
    match = rule.get('match', {})
    if not isinstance(match, dict):
        raise RuleError('match must be an object')
    domains = match.get('domains', [])
    if not isinstance(domains, list) or not domains or len(domains)>30:
        raise RuleError('match.domains must contain 1-30 domains')
    for domain in domains:
        if not isinstance(domain, str) or not re.fullmatch(r'[a-z0-9.-]{3,255}', domain) or domain.startswith('.'):
            raise RuleError('Invalid match domain')
    patterns = match.get('path_patterns', ['*'])
    if not isinstance(patterns, list) or not patterns or any(not isinstance(v,str) or len(v)>200 for v in patterns):
        raise RuleError('Invalid path_patterns')
    if 'enabled' in rule and not isinstance(rule['enabled'],bool):
        raise RuleError('enabled must be boolean')
    if set(rule)-{'schema_version','id','name','match','fields','enabled','page'}:
        raise RuleError('Unsupported top-level rule properties')
    page = rule.get('page', {})
    if not isinstance(page, dict) or set(page) - {'extra_wait_seconds'}:
        raise RuleError('page only supports extra_wait_seconds')
    if 'extra_wait_seconds' in page and (type(page['extra_wait_seconds']) is not int or
                                          not 0 <= page['extra_wait_seconds'] <= 30):
        raise RuleError('page.extra_wait_seconds must be an integer from 0 to 30')
    fields = rule.get('fields')
    if not isinstance(fields, dict) or not fields or not set(fields).issubset(ALLOWED_FIELDS):
        raise RuleError('Unknown or empty product fields')
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            raise RuleError(f'{name}: field definition must be an object')
        # Fixed currency is an alternative to selectors, never a fallback.
        if name == 'currency' and 'literal' in spec:
            value = spec['literal']
            if (set(spec) != {'literal'} or not isinstance(value, str) or
                    not re.fullmatch(r'[A-Z]{3}', value) or
                    value not in get_global('all_currencies')):
                raise RuleError('currency.literal must be a recognized uppercase ISO 4217 code and cannot be combined with selectors')
            continue
        if 'condition' in spec:
            if name not in ('in_stock', 'pickup', 'shipping') or set(spec) != {'condition'}:
                raise RuleError(f'{name}: conditions are only valid for stock and purchase channels')
            _validate_condition(spec['condition'], name)
            continue
        if set(spec) - {'selectors','type','value','selector','extract','attribute','mapping'}:
            raise RuleError(f'{name}: unsupported field properties')
        selectors = spec.get('selectors') or [spec]
        if not isinstance(selectors, list) or not 1 <= len(selectors) <= 8:
            raise RuleError(f'{name}: expected 1-8 selectors')
        for selector in selectors:_validate_selector(selector, name)
        if name in ('in_stock','pickup','shipping'):
            mapping = spec.get('mapping', {})
            if not isinstance(mapping,dict) or not set(mapping).issubset({'in_stock','out_of_stock','unknown'}):
                raise RuleError('Invalid stock mapping')
            if any(not isinstance(v,list) or len(v)>30 or any(not isinstance(vv,str) or len(vv)>100 for vv in v) for v in mapping.values()):
                raise RuleError('Invalid stock match values')
    if len(json.dumps(rule,ensure_ascii=False).encode('utf-8'))>MAX_RULE_BYTES:
        raise RuleError('Rule exceeds size limit')
    return copy.deepcopy(rule)


def list_rules():
    result=[]
    directory=root()/'rules'
    if not directory.exists():
        return result
    for path in sorted(directory.glob('*.json')):
        try:
            rule=load(path.stem)
            result.append({'id':rule['id'],'name':rule['name'],'domains':rule['match']['domains'],'enabled':rule.get('enabled',True),'revision':signature(rule)})
        except (RuleError, ValueError, OSError):
            continue
    return result


def load(rid):
    if not isinstance(rid,str) or not ID.fullmatch(rid):
        raise RuleError('Invalid rule id')
    try:
        directory=root()/'rules'
        if directory.is_symlink():raise RuleError('Symlinked rules directory is not allowed')
        filepath=directory/(rid+'.json')
        if filepath.is_symlink():raise RuleError('Symlinked rule files are not allowed')
        data=filepath.read_bytes()
        if len(data)>MAX_RULE_BYTES:
            raise RuleError('Rule too large')
        obj=validate(json.loads(data))
        if obj['id']!=rid:
            raise RuleError('Rule ID and filename differ')
        return obj
    except FileNotFoundError as exc:
        raise RuleError(f'Rule not found: {rid}') from exc
    except json.JSONDecodeError as exc:
        raise RuleError(f'Invalid JSON: {exc.msg}') from exc


def save(rule, *, expected_signature=None, overwrite=False, return_status=False):
    """Atomic revision-checked saves; ID is stable, no UUID or silent overwrite."""
    rule=validate(rule)
    target=root()/'rules'
    if target.is_symlink():raise RuleError('Symlinked rules directory is not allowed')
    target.mkdir(parents=True,exist_ok=True)
    data=(json.dumps(rule,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    filepath=target/(rule['id']+'.json')
    with WRITE_LOCK:
        if filepath.is_symlink():raise RuleError('Symlinked rule file is not allowed')
        existing=None
        if filepath.exists():
            existing=load(rule['id'])
            if existing==rule:
                return (rule,'unchanged') if return_status else rule
            if not overwrite:
                raise RuleError('Rule ID already exists with different content; confirm overwrite')
            if not expected_signature or expected_signature!=signature(existing):
                raise RuleError('Rule changed since opening; reload before overwriting')
            status='updated'
        else:
            if expected_signature:
                raise RuleError('Rule was deleted or renamed since opening')
            status='created'
        fd,tmp=tempfile.mkstemp(prefix='.rule-',suffix='.tmp',dir=target)
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            os.replace(tmp,filepath)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    return (rule,status) if return_status else rule


def remove(rid, *, expected_signature=None):
    """Delete only the exact revision the user confirmed."""
    with WRITE_LOCK:
        rule=load(rid)
        if not expected_signature or signature(rule)!=expected_signature:
            raise RuleError('Rule changed since opening; reload before deleting')
        filepath=root()/'rules'/(rid+'.json')
        if filepath.is_symlink():raise RuleError('Symlinked rule file is not allowed')
        filepath.unlink()


def matches(rule,url):
    parts=urlsplit(url)
    if parts.scheme not in ('http','https') or not parts.hostname:
        return False
    host=parts.hostname.lower()
    domains=rule['match']['domains']
    if not any(host==domain or host.endswith('.'+domain) for domain in domains):
        return False
    return any(fnmatch.fnmatchcase(parts.path or '/',pattern) for pattern in rule['match'].get('path_patterns',['*']))


def choose(url,mode='auto',rid=''):
    if mode=='builtin':
        return None
    if mode=='rule':
        rule=load(rid)
        if not rule.get('enabled',True):
            raise RuleError('Selected rule is disabled')
        if not matches(rule,url):
            raise RuleError('Selected rule does not match Watch URL')
        return rule
    if mode!='auto':
        raise RuleError('Unknown extraction mode')
    choices=[load(info['id']) for info in list_rules() if info['enabled']]
    found=[rule for rule in choices if matches(rule,url)]
    if len(found)>1:
        raise RuleError('Multiple product rules match; select a rule explicitly')
    return found[0] if found else None


def signature(rule):
    if not rule:return 'builtin'
    return hashlib.sha256(json.dumps(rule,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()


def extraction_signature(rule):
    """Hash only extraction semantics; metadata and page waits do not reset baselines."""
    if rule is None:
        return 'builtin'
    payload = {'id': rule['id'], 'fields': rule['fields']}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def matching_rules(url):
    """The same URL matcher used by scheduled checks and the Watch editor."""
    return [info for info in list_rules() if info['enabled'] and matches(load(info['id']), url)]
