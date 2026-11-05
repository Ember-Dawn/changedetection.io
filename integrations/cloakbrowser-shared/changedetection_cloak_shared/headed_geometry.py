"""Fit the actual Chromium X11 window into the virtual display.

Without a window manager, Chromium's start-maximized request may leave
unused black Xvfb desktop pixels beneath the browser window.
"""
import asyncio
import os
import re
import subprocess

from loguru import logger

WIDTH, HEIGHT = 1366, 900
CHROME_CLASS = r'(chrome|Chrome|chromium|Chromium)'


def _run(*args):
    return subprocess.run(
        ['xdotool', *map(str, args)],
        capture_output=True, text=True, timeout=3, check=False
    )


def _geometry(stdout):
    data = dict(re.findall(r'^([A-Z]+)=(-?\d+)$', stdout, re.MULTILINE))
    try:
        return tuple(int(data[k]) for k in ('X', 'Y', 'WIDTH', 'HEIGHT'))
    except (ValueError, KeyError):
        return None


def _fit_once():
    found = _run('search', '--onlyvisible', '--class', CHROME_CLASS)
    if found.returncode:
        return None
    ids = [s for s in found.stdout.splitlines() if s.strip().isdigit()]
    if not ids:
        return None
    window = ids[-1].strip()
    before = _geometry(_run('getwindowgeometry', '--shell', window).stdout)
    moved = _run('windowmove', window, 0, 0)
    sized = _run('windowsize', window, WIDTH, HEIGHT)
    after = _geometry(_run('getwindowgeometry', '--shell', window).stdout)
    return before, after, not (moved.returncode or sized.returncode) and after == (0, 0, WIDTH, HEIGHT)


async def fit_headed_window():
    """Best effort; never disrupt Profile or BrowserManager recovery."""
    if not os.environ.get('DISPLAY'):
        logger.warning('Live Browser: DISPLAY missing for X11 geometry adjustment')
        return False
    for attempt in range(12):
        try:
            result = await asyncio.to_thread(_fit_once)
            if result is not None:
                before, after, success = result
                if success:
                    logger.info('Live Chromium X11 geometry {} -> {}', before, after)
                    return True
                if attempt == 11:
                    logger.warning('Live Chromium X11 geometry still incorrect {} -> {}', before, after)
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning('Cannot adjust Live Chromium X11 geometry: {}', exc)
            return False
        await asyncio.sleep(.25)
    logger.warning('No visible Chromium X11 window found; desktop black strip may remain')
    return False
