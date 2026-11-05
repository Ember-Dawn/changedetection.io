"""Single Profile, single Chromium, temporary X11 desktop mode.

The normal BrowserManager owns both contexts. VNC listens on loopback only;
its only remote entry is the authenticated /manual-browser/live/ws route.
"""
import os
import shutil
import socket
import subprocess
import threading
import time

from changedetectionio import live_browser_gate
from .manager import manager
from .manual_session import manual_sessions


class LiveBrowserError(RuntimeError):
    pass


class LiveBrowserController:
    def __init__(self):
        self._lock = threading.RLock()
        self._phase = 'idle'
        self._owner = None
        self._error = None
        self._xvfb = None
        self._vnc = None
        self._display = os.getenv('CLOAKBROWSER_LIVE_DISPLAY', ':98')
        self._port = int(os.getenv('CLOAKBROWSER_LIVE_VNC_PORT', '5998'))

    def status(self, owner):
        with self._lock:
            return {'phase': self._phase, 'owned': self._owner == owner,
                    'active': self._phase == 'active', 'error': self._error}

    def allowed(self, owner):
        with self._lock:
            return self._phase == 'active' and self._owner == owner

    def vnc_target(self, owner):
        if not self.allowed(owner):
            raise LiveBrowserError('No live desktop belonging to this login')
        return '127.0.0.1', self._port

    def _stop_desktop(self):
        for name in ('_vnc', '_xvfb'):
            proc = getattr(self, name)
            if proc is None:
                continue
            if proc.poll() is None:
                proc.terminate()
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
            setattr(self, name, None)

    def _start_desktop(self):
        for name in ('Xvfb', 'x11vnc'):
            if not shutil.which(name):
                raise LiveBrowserError(f'{name} not installed in Docker image')
        # One DISPLAY in this single-process app. Reserve the VNC loopback port;
        # x11vnc binds it only locally and is never published in Compose.
        self._xvfb = subprocess.Popen(['Xvfb', self._display, '-screen', '0',
                                       '1366x900x24', '-nolisten', 'tcp'],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.environ['DISPLAY'] = self._display
        time.sleep(1)
        if self._xvfb.poll() is not None:
            raise LiveBrowserError('Xvfb failed; check DISPLAY availability')
        self._vnc = subprocess.Popen(['x11vnc', '-display', self._display,
                                      '-localhost', '-rfbport', str(self._port),
                                      '-nopw', '-forever', '-shared', '-noxdamage'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self._vnc.poll() is not None:
                raise LiveBrowserError('x11vnc failed to start')
            try:
                with socket.create_connection(('127.0.0.1', self._port), 0.3):
                    return
            except OSError:
                time.sleep(0.1)
        raise LiveBrowserError('x11vnc not listening on loopback')

    def start(self, owner):
        with self._lock:
            if self._phase != 'idle':
                raise LiveBrowserError('Live Browser is already active or transitioning')
            self._phase, self._owner, self._error = 'starting', owner, None
        live_browser_gate.pause()
        try:
            if not live_browser_gate.drain(timeout=90):
                raise LiveBrowserError('Running Watch tasks did not finish within 90 seconds')
            if manual_sessions.inspect(owner).get('active') or manual_sessions.inspect(owner).get('opening'):
                raise LiveBrowserError('Close the existing manual browser session first')
            stats = manager.status()
            if stats['active_jobs'] or stats['preview_operations'] or stats['active_pages']:
                raise LiveBrowserError('Browser has active preview or page leases; close them first')
            self._start_desktop()
            manager.switch_live_mode(True)
            with self._lock:
                self._phase = 'active'
        except BaseException as exc:
            self._error = str(exc)
            # A failed mode launch can leave Profile closure uncertain. Fail
            # closed rather than admitting worker jobs on a damaged browser.
            try:
                if manager.status()['mode'] == 'headed':
                    manager.switch_live_mode(False)
                self._stop_desktop()
                live_browser_gate.resume()
                with self._lock:
                    self._phase, self._owner = 'idle', None
            except BaseException:
                with self._lock:
                    self._phase = 'error'
            raise LiveBrowserError(str(exc)) from exc
        return self.status(owner)

    def stop(self, owner):
        with self._lock:
            if self._owner != owner or self._phase not in ('active', 'error'):
                raise LiveBrowserError('Live Browser is not owned by this login')
            self._phase = 'stopping'
        try:
            manager.switch_live_mode(False)
            self._stop_desktop()
            live_browser_gate.resume()
            with self._lock:
                self._phase, self._owner, self._error = 'idle', None, None
        except BaseException as exc:
            with self._lock:
                self._phase, self._error = 'error', str(exc)
            raise LiveBrowserError('Unable to restore Headless: ' + str(exc)) from exc
        return self.status(owner)


live_browser = LiveBrowserController()
