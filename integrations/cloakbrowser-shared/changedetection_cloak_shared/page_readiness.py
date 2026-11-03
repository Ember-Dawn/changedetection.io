"""Conservative challenge/interstitial detection and passive page readiness.

This does not solve CAPTCHA or bypass website security checks.
"""
import asyncio
import html
import os
import re
import time
from loguru import logger


def _seconds(name, default, maximum):
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        logger.warning('Invalid {} value; using {}', name, default)
        return default
    if not 0 <= value <= maximum:
        logger.warning('Out-of-range {} value; using {}', name, default)
        return default
    return value


def challenge_kind(text, *, url='', title=''):
    """Recognize specific interstitials; None means not confidently recognized."""
    if not isinstance(text, str) or len(text) > 24000:
        return None
    combined = html.unescape(text).lower()
    combined = re.sub(r'<[^>]{0,300}>', ' ', combined)
    combined = re.sub(r'\s+', ' ', combined)
    title = (title or '').lower()
    url = (url or '').lower()

    cf_challenge = any(s in combined for s in (
        'performing security verification',
        'checking if the site connection is secure',
        'verify you are human', 'verifying you are human',
        'checking your browser before accessing',
    ))
    cf_vendor = any(s in combined for s in (
        'cloudflare', 'cf-challenge', 'challenges.cloudflare.com',
        'security service to protect against malicious bots',
    ))
    if (cf_challenge and cf_vendor) or ('just a moment' in title and cf_vendor):
        return 'Cloudflare verification'

    google_traffic = any(s in combined for s in (
        'unusual traffic from your computer network',
        'automated queries', '异常流量', '异常的流量', '自动发送的请求',
    ))
    google_context = any(s in combined for s in (
        'recaptcha', 'not a robot', '不是机器人', 'google',
    )) or ('google.com/sorry' in url)
    if google_traffic and google_context:
        return 'Google verification'
    if 'google.com/sorry' in url and ('captcha' in combined or 'recaptcha' in combined):
        return 'Google verification'
    return None


async def page_challenge(page):
    """Inspect visible text rather than merely searching for embedded widgets."""
    try:
        info = await page.evaluate("""() => ({
            title: document.title || '',
            text: (document.body && document.body.innerText || '').slice(0, 12000),
            url: location.href
        })""")
        if not isinstance(info, dict):
            return None
        return challenge_kind(info.get('text', ''), url=info.get('url', ''), title=info.get('title', ''))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.debug('Unable to inspect page challenge state: {}', exc)
        return None


async def wait_for_page_ready(page):
    """Passive delay, followed by bounded wait if a challenge remains visible."""
    settle = _seconds('CLOAKBROWSER_PAGE_SETTLE_SECONDS', 2, 30)
    if settle:
        await asyncio.sleep(settle)
    kind = await page_challenge(page)
    if not kind:
        return None
    budget = _seconds('CLOAKBROWSER_CHALLENGE_WAIT_SECONDS', 15, 90)
    deadline = time.monotonic() + budget
    logger.info('{} displayed; waiting up to {}s for normal page transition', kind, budget)
    while kind and time.monotonic() < deadline:
        await asyncio.sleep(min(1, max(0, deadline - time.monotonic())))
        kind = await page_challenge(page)
    return kind
