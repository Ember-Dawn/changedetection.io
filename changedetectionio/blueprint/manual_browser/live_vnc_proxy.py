"""Authenticate noVNC RFC6455 upgrade and relay raw RFB bytes to loopback VNC.

No public container or host VNC listener. The RFB stream is opaque; all
connections belong to the authenticated, current live-desktop controller.
"""
import socket
import threading
from flask import request
from flask_wtf.csrf import validate_csrf, ValidationError
from simple_websocket import Server, ConnectionClosed


def relay(owner, controller):
    # Validate before accepting a WebSocket upgrade.
    token = request.args.get('csrf', '')
    try:
        validate_csrf(token)
    except (ValidationError, TypeError, ValueError):
        return ('Invalid CSRF token', 403)
    if not controller.allowed(owner):
        return ('Live browser is not active for this login', 403)
    # The caller also checks Origin/Host on this sensitive endpoint.
    target = controller.vnc_target(owner)
    try:
        upstream = socket.create_connection(target, timeout=5)
    except OSError:
        return ('VNC desktop unavailable', 503)
    upstream.settimeout(1)
    ws = None
    closed = threading.Event()
    try:
        ws = Server.accept(request.environ)
        def vnc_to_ws():
            try:
                while not closed.is_set() and controller.allowed(owner):
                    try:
                        data = upstream.recv(65536)
                    except socket.timeout:
                        continue
                    if not data: break
                    ws.send(data)
            except (OSError, ConnectionClosed):
                pass
            finally:
                closed.set()
        receiver = threading.Thread(target=vnc_to_ws, daemon=True)
        receiver.start()
        while not closed.is_set() and controller.allowed(owner):
            try:
                data = ws.receive(timeout=1)
            except (ConnectionClosed, OSError):
                break
            if data is None: continue
            if not isinstance(data, bytes):
                break
            try: upstream.sendall(data)
            except OSError: break
    finally:
        closed.set()
        try: upstream.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        upstream.close()
        if ws is not None:
            try: ws.close()
            except Exception: pass
    return ''
