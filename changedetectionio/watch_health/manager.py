"""Small watch-health state machine. A completed check is the accounting unit."""
import time

DEFAULTS = dict(reliability_wait_seconds=10, reliability_page_attempts=2,
                reliability_page_gap_seconds=10, reliability_failure_threshold=2,
                reliability_retry_minutes=5)
LIMITS = dict(reliability_wait_seconds=(0, 30), reliability_page_attempts=(1, 3),
              reliability_page_gap_seconds=(0, 60), reliability_failure_threshold=(1, 10),
              reliability_retry_minutes=(0, 1440))

def policy(datastore, watch):
    settings = datastore.data['settings']['requests']
    result = {}
    for key, (lower, upper) in LIMITS.items():
        raw = settings.get(key, DEFAULTS[key])
        if not watch.get('reliability_use_default', True):
            override = watch.get(key)
            if override is not None and override != '':
                raw = override
        try:
            number = int(raw)
        except (ValueError, TypeError):
            number = DEFAULTS[key]
        result[key] = max(lower, min(upper, number))
    return result

def retry_due(watch, now=None):
    stamp = float((watch.get('watch_health') or {}).get('next_retry_at') or 0)
    return bool(stamp and (now if now is not None else time.time()) >= stamp)

def record_result(datastore, uuid, result, *, reason='', category='', now=None):
    """Record exactly one completed check. result: success, failure, attention.

    Does not emit any normal content-change notification. All callers must
    call this once, after parsing succeeds OR a catch path finishes.
    """
    watch = datastore.data['watching'].get(uuid)
    if watch is None:
        return None
    now = time.time() if now is None else float(now)
    current = dict(watch.get('watch_health') or {})
    previous = current.get('status', 'unknown')
    cfg = policy(datastore, watch)
    if result == 'success':
        current.update(status='healthy', consecutive_failures=0, next_retry_at=0,
                       last_success_at=now, last_error='', error_category='')
    elif result == 'attention':
        current.update(status='action_required', next_retry_at=0, last_error=str(reason)[:500],
                       error_category='verification', consecutive_failures=int(current.get('consecutive_failures') or 0)+1)
    elif result == 'failure':
        failures = int(current.get('consecutive_failures') or 0)+1
        threshold = cfg['reliability_failure_threshold']
        status = 'failed' if failures >= threshold else 'degraded'
        interval = cfg['reliability_retry_minutes']
        # Explicitly disabled (0) means no accelerated recheck.
        next_retry = now + 60 * interval if interval else 0
        current.update(status=status, consecutive_failures=failures, next_retry_at=next_retry,
                       last_error=str(reason)[:500], error_category=str(category)[:80])
    else:
        raise ValueError('Unknown check health result')
    if previous != current['status']:
        current['status_changed_at'] = now
    datastore.update_watch(uuid=uuid, update_obj={'watch_health': current})
    return previous, current['status']
