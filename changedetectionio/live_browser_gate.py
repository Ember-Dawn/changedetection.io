"""Process-wide admission gate for the one-Profile live desktop maintenance window.

The gate does not persist or modify the user's all_paused setting. Worker jobs
are retained in the queue; only started work is counted toward the drain.
"""
import threading
import time

_lock = threading.Condition(threading.RLock())
_paused = False
_active = 0


def begin_job():
    global _active
    with _lock:
        if _paused:
            return False
        _active += 1
        return True


def end_job():
    global _active
    with _lock:
        if _active <= 0:
            raise RuntimeError('Live browser work admission counter underflow')
        _active -= 1
        _lock.notify_all()


def pause():
    global _paused
    with _lock:
        _paused = True


def resume():
    global _paused
    with _lock:
        _paused = False
        _lock.notify_all()


def is_paused():
    with _lock:
        return _paused


def drain(timeout=90):
    with _lock:
        deadline = time.monotonic() + timeout
        while _active:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            _lock.wait(remaining)
        return True


def status():
    with _lock:
        return {'paused': _paused, 'active_jobs': _active}
