"""Spacing for scheduled shared-browser top-level page navigations only.

The coordinator is used on BrowserManager's asyncio loop. It does NOT limit
images, XHR, scripts, manual browsing, or different sites. Domain extraction
uses an offline Public Suffix List snapshot bundled by tldextract.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from urllib.parse import urlsplit

_EXTRACT = None
_DOMAIN = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def normalize_domain(raw):
    value = str(raw or '').strip().lower().rstrip('.')
    if '://' in value or '/' in value or ':' in value or not _DOMAIN.fullmatch(value):
        raise ValueError('Enter a domain only, for example microcenter.com')
    if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
           for label in value.split('.')):
        raise ValueError('Invalid domain label')
    if value != 'localhost' and '.' not in value:
        raise ValueError('Enter a complete domain')
    return value


def parse_overrides(text):
    """Domain = seconds, one rule per line; validated before settings save."""
    rules = {}
    for number, line in enumerate(str(text or '').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split('=')
        if len(parts) != 2:
            raise ValueError(f'Line {number}: expected domain = seconds')
        domain = normalize_domain(parts[0])
        try:
            seconds = float(parts[1].strip())
        except ValueError as exc:
            raise ValueError(f'Line {number}: seconds must be a number') from exc
        if not (0 <= seconds <= 3600) or not seconds < float('inf'):
            raise ValueError(f'Line {number}: interval must be 0 to 3600 seconds')
        if domain in rules:
            raise ValueError(f'Line {number}: duplicate domain {domain}')
        rules[domain] = seconds
    return rules


def site_key(url):
    parts = urlsplit(url)
    hostname = (parts.hostname or '').lower().rstrip('.')
    if not hostname:
        return ''
    try:
        ipaddress.ip_address(hostname)
        return hostname
    except ValueError:
        pass
    if hostname == 'localhost':
        return hostname
    # Offline PSL snapshot: no network calls or startup update checks.
    global _EXTRACT
    if _EXTRACT is None:
        import tldextract
        _EXTRACT = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
    result = _EXTRACT(hostname)
    return result.top_domain_under_public_suffix or hostname


def effective_interval(site, settings):
    rules = parse_overrides(settings.get('site_interval_overrides') or '')
    default = float(settings.get('site_interval_seconds', 3) or 0)
    return rules.get(site, default)


class SiteNavigationPacer:
    """Non-blocking async spacing, never holds a global lock while sleeping.

    A short per-site lock reserves timestamps atomically so two navigations
    scheduled at the same instant cannot both bypass the interval.
    """
    def __init__(self, *, clock=time.monotonic, sleep=asyncio.sleep):
        self._clock = clock
        self._sleep = sleep
        self._last = {}
        self._locks = {}

    async def wait_turn(self, url, settings):
        site = site_key(url)
        if not site:
            return
        interval = effective_interval(site, settings)
        lock = self._locks.setdefault(site, asyncio.Lock())
        async with lock:
            previous = self._last.get(site)
            if previous is not None and interval > 0:
                remaining = previous + interval - self._clock()
                if remaining > 0:
                    await self._sleep(remaining)
            # Commit immediately before goto. Cancellation during the wait
            # cannot consume another reservation.
            self._last[site] = self._clock()
