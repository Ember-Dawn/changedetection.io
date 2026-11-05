"""Bounded declarative extraction: no Python/JavaScript execution."""
import json
import re
from bs4 import BeautifulSoup
from lxml import html as lxml_html
from .models import ProductData, RuleError, money
from .registry import validate


def _extract_one(document, selector, parsed):
    expr=selector.get('value') or selector.get('selector')
    typ=selector['type']
    how=selector.get('extract','text')
    if typ=='css':
        if 'soup' not in parsed: parsed['soup']=BeautifulSoup(document,'lxml')
        nodes=parsed['soup'].select(expr,limit=30)
        if how=='attr': return [n.get(selector['attribute']) for n in nodes]
        if how=='html':return [str(n) for n in nodes]
        return [n.get_text(' ',strip=True) if how=='text' else n.get('value') for n in nodes]
    if typ=='xpath':
        if 'xpath' not in parsed:parsed['xpath']=lxml_html.fromstring(document)
        nodes=parsed['xpath'].xpath(expr)
        if not isinstance(nodes,list): nodes=[nodes]
        if len(nodes)>30:raise RuleError('XPath matched more than 30 values')
        if how=='attr':return [node.get(selector['attribute']) for node in nodes if hasattr(node,'get')]
        if how=='html':return [lxml_html.tostring(node,encoding='unicode') if hasattr(node,'tag') else str(node) for node in nodes]
        return [' '.join(node.itertext()).strip() if hasattr(node,'itertext') else str(node) for node in nodes]
    if typ=='regex':
        # Keep expressions deliberately simple: no nested capture/quantifier
        # structures that can cause catastrophic backtracking on untrusted HTML.
        if len(expr)>160 or re.search(r'\([^)]*[+*][^)]*\)[+*{]',expr):
            raise RuleError('Unsupported or oversized regular expression')
        try:
            import regex as regex_engine  # already required by the application
        except ImportError:
            regex_engine=None  # portable unit-test environment only
        if regex_engine is not None:
            iterator=regex_engine.finditer(expr,document[:200000], timeout=0.15)
        else:
            iterator=re.finditer(expr,document[:12000])
        values=[]
        for match in iterator:
            values.append(match.group(1) if match.lastindex else match.group())
            if len(values)>=30:break
        return values
    if typ=='jsonpath':
        from jsonpath_ng.ext import parse as jsonpath_parse
        if 'soup' not in parsed:parsed['soup']=BeautifulSoup(document,'lxml')
        soup=parsed['soup']
        results=[]
        for script in soup.select('script[type="application/ld+json"]')[:15]:
            try: data=json.loads(script.string or script.get_text())
            except (ValueError,TypeError):continue
            results.extend([m.value for m in jsonpath_parse(expr).find(data)])
            if len(results)>30:raise RuleError('JSONPath matched more than 30 values')
        return results
    raise RuleError('Unsupported selector')


def _tri_any(values):
    return True if True in values else None if None in values else False


def _tri_all(values):
    return False if False in values else None if None in values else True


def _condition(expr, document, parsed, fields):
    op = expr['op']
    if op == 'literal':return expr['value']
    if op == 'ref':return fields.get(expr['field'])
    if op in ('any','all','coalesce'):
        results = [_condition(item, document, parsed, fields) for item in expr['items']]
        if op == 'any':return _tri_any(results)
        if op == 'all':return _tri_all(results)
        return next((v for v in results if v is not None), None)
    if op == 'not':
        value = _condition(expr['item'], document, parsed, fields)
        return None if value is None else not value
    if op == 'if':
        condition = _condition(expr['test'], document, parsed, fields)
        return _condition(expr['then' if condition else 'else'], document, parsed, fields) if condition is not None else None
    if 'guard' in expr:
        if not any(v is not None for v in _extract_one(document,expr['guard'],parsed)):
            return None
    values = [str(v).strip() for v in _extract_one(document,expr['selector'],parsed) if v is not None]
    if op == 'exists':return bool(values)
    if not values:return None
    if op == 'contains':return any(expr['value'].casefold() in value.casefold() for value in values)
    if op == 'equals':return any(expr['value'].casefold() == value.casefold() for value in values)
    raise RuleError('Unsupported condition')


def evaluate(rule,document):
    rule = validate(rule)
    if not isinstance(document,str) or len(document)>8_000_000:
        raise RuleError('HTML must be a string smaller than 8 MB')
    parsed = {}
    result = ProductData(rule_id=rule['id'])
    conditions = {}
    for field,spec in rule['fields'].items():
        if field == 'currency' and 'literal' in spec:
            result.currency = spec['literal']
            result.field_details[field] = {'literal': spec['literal'], 'matches': None, 'selector': None, 'values': [spec['literal']]}
            continue
        if 'condition' in spec:
            conditions[field] = spec['condition']
            continue
        choices=spec.get('selectors') or [spec]
        matches=[];used=None
        for selector in choices:
            try:values=_extract_one(document,selector,parsed)
            except Exception as exc:
                raise RuleError(f'{field}: selector failed: {type(exc).__name__}') from exc
            matches=[v for v in values if v is not None and str(v).strip()]
            if matches:
                used=selector;break
        unique=list(dict.fromkeys(str(v).strip() for v in matches))
        result.field_details[field]={'matches':len(matches),'selector':used,'values':unique[:5]}
        if not unique:continue
        if field in ('in_stock','pickup','shipping'):
            mapping=spec.get('mapping',{})
            statuses=set()
            for value in unique:
                lower=value.lower()
                for status, phrases in mapping.items():
                    if any(p.lower() in lower for p in phrases):statuses.add(status)
                if lower in ('true','false'):
                    statuses.add('in_stock' if lower=='true' else 'out_of_stock')
            if len(statuses)>1:raise RuleError(f'Ambiguous {field} status')
            setattr(result,field,True if 'in_stock' in statuses else False if 'out_of_stock' in statuses else None)
        elif field=='price':
            amounts={money(v) for v in unique}
            if len(amounts)>1:raise RuleError('Ambiguous product price: multiple amounts')
            result.price=next(iter(amounts))
        elif field=='stock_quantity':
            nums={int(re.sub(r'[^0-9]','',v)) for v in unique if re.search(r'\d',v)}
            if len(nums)>1:raise RuleError('Ambiguous inventory quantity')
            result.stock_quantity=next(iter(nums)) if nums else None
        else:
            if len(unique)>1:raise RuleError(f'Ambiguous {field}: multiple values')
            value=unique[0]
            if field=='currency':
                if not re.fullmatch(r'[A-Za-z]{3}',value):raise RuleError('Currency must be ISO three-letter code')
                value=value.upper()
            setattr(result,field,value)
    # Resolve independent purchase channels first, then derived stock state.
    for field in ('pickup','shipping','in_stock'):
        if field not in conditions:continue
        try:
            value=_condition(conditions[field],document,parsed,result.to_dict())
        except Exception as exc:
            raise RuleError(f'{field}: condition failed: {type(exc).__name__}') from exc
        setattr(result,field,value)
        result.field_details[field]={'condition':conditions[field]['op'],'value':value,'matches':None}
    if result.in_stock is None and 'in_stock' not in conditions and (result.pickup is not None or result.shipping is not None):
        result.in_stock=_tri_any([result.pickup,result.shipping])
    if result.in_stock is None and 'in_stock' not in conditions and result.stock_quantity is not None:
        result.in_stock=result.stock_quantity>0
    if result.price is None and result.in_stock is None:
        raise RuleError('No usable price or stock data extracted')
    return result
