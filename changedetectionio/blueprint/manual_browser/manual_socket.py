"""Authenticated Socket.IO transport for the existing manual browser session.

No browser objects are owned by the socket threads. Every Page operation runs
through ManualSessionManager -> BrowserManager's dedicated asyncio loop.
"""
import os
import threading
import time
from urllib.parse import urlsplit

from flask import current_app, request, session
from flask_login import current_user
from flask_socketio import Namespace
from flask_wtf.csrf import ValidationError, validate_csrf
from loguru import logger

from changedetection_cloak_shared.manual_session import ManualSessionError, manual_sessions

INPUT_NS = '/manual-input'
FRAME_NS = '/manual-frames'


def _authorize(auth):
    """Never authorize using the permissive global status-socket policy."""
    if not isinstance(auth, dict):
        return None
    datastore = current_app.config.get('DATASTORE')
    if datastore is None:
        return None
    app_settings = datastore.data['settings']['application']
    if (not (app_settings.get('password') or os.getenv('SALTED_PASS')) or
            current_app.config.get('LOGIN_DISABLED') or not current_user.is_authenticated):
        return None
    origin = request.headers.get('Origin')
    if origin and urlsplit(origin).netloc.lower() != request.host.lower():
        return None
    try:
        validate_csrf(auth.get('csrf') or '')
    except (ValidationError, TypeError, ValueError):
        return None
    owner = session.get('_manual_browser_owner')
    token = auth.get('session')
    generation = auth.get('generation')
    if not owner or not isinstance(token, str) or len(token) > 128 or type(generation) is not int:
        return None
    try:
        manual_sessions.authorize(token, owner, generation)
    except ManualSessionError:
        return None
    return token, owner, generation


class ManualInputNamespace(Namespace):
    def __init__(self):
        super().__init__(INPUT_NS)
        self._lock = threading.RLock()
        self._clients = {}
        self._controller = None

    def on_connect(self, auth=None):
        credentials = _authorize(auth)
        if credentials is None:
            return False
        with self._lock:
            if self._controller is not None:
                return False
            self._controller = request.sid
            self._clients[request.sid] = {'identity': credentials, 'seq': -1}

    def on_disconnect(self, reason=None):
        sid = request.sid
        with self._lock:
            client = self._clients.pop(sid, None)
            if self._controller == sid:
                self._controller = None
        if client:
            token, owner, _ = client['identity']
            # A disconnected pointerdown must not strand the remote button.
            try:
                manual_sessions.release_pointer(token, owner)
            except Exception:
                pass

    def on_action(self, data):
        sid = request.sid
        if not isinstance(data, dict):
            return {'ok': False, 'error': 'Invalid input payload'}
        with self._lock:
            client = self._clients.get(sid)
            if not client or sid != self._controller:
                return {'ok': False, 'error': 'Input control is no longer active'}
            seq = data.get('seq')
            if type(seq) is not int or seq <= client['seq']:
                return {'ok': False, 'error': 'Out-of-order input sequence'}
            client['seq'] = seq
            token, owner, generation = client['identity']
            action = data.get('action')
            if action not in {'move', 'down', 'up', 'click', 'scroll', 'resize',
                              'key', 'text', 'navigate', 'back', 'forward', 'refresh'}:
                return {'ok': False, 'error': 'Unsupported manual action'}
            try:
                manual_sessions.authorize(token, owner, generation)
                # Same ManualSession action validation as HTTP; no new URL or
                # keyboard capability granted by the transport.
                result = manual_sessions.action(token, owner, action, data)
                return {'ok': True, 'seq': seq, 'result': result}
            except ManualSessionError as exc:
                return {'ok': False, 'seq': seq, 'terminal': True, 'error': str(exc)}
            except Exception as exc:
                logger.warning('Manual socket input failed: {}', type(exc).__name__)
                return {'ok': False, 'seq': seq, 'error': 'Browser input failed'}


class ManualFramesNamespace(Namespace):
    def __init__(self, socketio):
        super().__init__(FRAME_NS)
        self.socketio = socketio
        self._lock = threading.RLock()
        self._clients = {}

    def on_connect(self, auth=None):
        credentials = _authorize(auth)
        if credentials is None:
            return False
        sid = request.sid
        with self._lock:
            if self._clients:
                return False  # One viewer, one JPEG producer per manual Page.
            client = {'identity': credentials, 'sid': sid, 'alive': True,
                      'active': True, 'last_input': time.monotonic(),
                      'ack': threading.Event(), 'seq': 0}
            self._clients[sid] = client
        self.socketio.start_background_task(self._produce, client)

    def on_disconnect(self, reason=None):
        with self._lock:
            client = self._clients.pop(request.sid, None)
            if client:
                client['alive'] = False
                client['ack'].set()

    def on_frame_ack(self, data):
        with self._lock:
            client = self._clients.get(request.sid)
            if client and isinstance(data, dict) and data.get('seq') == client['seq']:
                client['ack'].set()

    def on_view(self, data):
        with self._lock:
            client = self._clients.get(request.sid)
            if client:
                client['active'] = isinstance(data, dict) and data.get('active') is True
                # Wake a pending frame on both pause and resume; pausing
                # must not falsely trigger the 6-second stream timeout.
                client['ack'].set()

    def on_interaction(self, data=None):
        with self._lock:
            client = self._clients.get(request.sid)
            if client:
                client['last_input'] = time.monotonic()

    def _produce(self, client):
        token, owner, generation = client['identity']
        self.socketio.sleep(0.1)  # Allow the namespace CONNECT packet to finish.
        while client['alive']:
            if not client['active']:
                self.socketio.sleep(0.2)
                continue
            started = time.monotonic()
            try:
                manual_sessions.authorize(token, owner, generation)
                jpeg = manual_sessions.frame(token, owner)
                if not client['alive']:
                    break
                client['ack'].clear()
                client['seq'] += 1
                self.socketio.emit('frame', {'seq': client['seq'], 'jpeg': jpeg,
                                             'capture_ms': round((time.monotonic()-started)*1000)},
                                   to=client['sid'], namespace=FRAME_NS)
                # One frame in flight; stall instead of queueing unlimited JPEGs.
                deadline = time.monotonic() + 6
                while client['alive'] and not client['ack'].is_set() and time.monotonic() < deadline:
                    self.socketio.sleep(0.02)
                if not client['alive'] or not client['ack'].is_set():
                    break
            except Exception as exc:
                logger.debug('Manual frame stream stopped: {}', type(exc).__name__)
                break
            if not client['alive']:
                break
            idle = time.monotonic() - client['last_input']
            delay = 0.1 if idle < 3.5 else 0.2 if idle < 15 else 0.5
            self.socketio.sleep(max(0.0, delay - (time.monotonic() - started)))
        client['alive'] = False
        with self._lock:
            self._clients.pop(client['sid'], None)
        # A transport failure is terminal for this frame channel; the client
        # falls back to HTTP, rather than leaving a stale second producer.
        try:
            self.socketio.emit('stream_end', {'error': 'Frame stream stopped'},
                               to=client['sid'], namespace=FRAME_NS)
        except Exception:
            pass


def register_manual_socketio(socketio):
    socketio.on_namespace(ManualInputNamespace())
    socketio.on_namespace(ManualFramesNamespace(socketio))
