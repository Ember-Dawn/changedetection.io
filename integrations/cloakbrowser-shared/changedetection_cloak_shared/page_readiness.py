"""Conservative challenge/interstitial detection for shared browser pages.

This does not solve CAPTCHA or bypass website security checks.
"""
import asyncio
import html
import re
from loguru import logger


def challenge_kind(text, *, url='', title=''):
    """Recognize specific interstitials; None means not confidently recognized."""
    if not isinstance(text, str):
        return None
    # Check a bounded prefix without ignoring large pages altogether.
    combined = html.unescape(text[:24000]).lower()
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
    # Google Scholar localized CAPTCHA pages often say only 人机身份验证,
    # without 'unusual traffic', while embedding a reCAPTCHA checkbox.
    scholar_url = 'scholar.google.' in url or 'google.com.hk/' in url
    localized_gate = any(s in combined for s in (
        '请进行人机身份验证', '进行人机身份验证', '请进行人机验证',
        'confirm you are human', 'verify that you are human',
    ))
    if scholar_url and localized_gate and any(s in combined for s in ('recaptcha', '人机', '机器人')):
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


