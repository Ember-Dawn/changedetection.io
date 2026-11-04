"""Product extraction entry point shared by dry-run and scheduled watches."""
from .models import ProductData, RuleError
from .registry import choose, signature, load, save, remove, list_rules
from .evaluator import evaluate


def extract(content, url, mode='auto', rule_id=''):
    rule=choose(url,mode,rule_id)
    return (evaluate(rule,content),rule) if rule else (None,None)
