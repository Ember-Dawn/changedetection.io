"""Validity of a rule-extracted retail product observation.

Stock must be explicit. An out-of-stock product may legitimately have no
price; an in-stock product normally must have one. Do not infer stock from
missing prices or from the monitoring policy.
"""


def observation_error(stock, price):
    """Return an actionable error, or None for a usable observation."""
    if stock is not True and stock is not False:
        return 'Product extraction rule failed: stock status is unavailable; check the JSON stock rule'
    if stock is True and price is None:
        return 'Product extraction rule failed: in-stock product price is unavailable; check the JSON price rule'
    return None


def observation_ready(stock, price):
    """Only a complete, usable observation ends the page readiness wait."""
    return observation_error(stock, price) is None
