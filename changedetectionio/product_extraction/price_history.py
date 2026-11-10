"""Append-only price/stock observations for each completed product check.

One JSONL file per Watch. A process-local per-watch lock synchronizes append/clear;
the application runs as one process, per AGENTS.md. The generation counter prevents
an in-flight check started before Clear History from repopulating cleared data.
"""
import json
import math
import os
import threading
from collections import defaultdict
from pathlib import Path

_LOCK = threading.RLock()
_GENERATIONS = defaultdict(int)
_FILENAME = 'price-history.jsonl'


def generation(data_dir):
    with _LOCK:
        return _GENERATIONS[str(data_dir)]


def append(data_dir, *, timestamp, price, in_stock, currency='', status='success', expected_generation=None):
    if not data_dir:
        return False
    directory = Path(data_dir)
    if price is not None:
        try:
            price = float(price)
        except (ValueError, TypeError):
            price = None
        if price is not None and not math.isfinite(price):
            price = None
    if in_stock is not None and not isinstance(in_stock, bool):
        in_stock = None
    point = {'timestamp': int(timestamp), 'price': price, 'in_stock': in_stock,
             'currency': str(currency or '')[:8], 'status': status}
    with _LOCK:
        if expected_generation is not None and _GENERATIONS[str(data_dir)] != expected_generation:
            return False
        # A deleted Watch must not be recreated by an in-flight worker.
        if not directory.is_dir():
            return False
        filename = directory / _FILENAME
        with open(filename, 'a', encoding='utf-8') as stream:
            stream.write(json.dumps(point, ensure_ascii=False, separators=(',', ':')) + '\n')
        return True


def has_records(data_dir):
    filename = Path(data_dir) / _FILENAME
    with _LOCK:
        return filename.is_file() and filename.stat().st_size > 0


def latest(data_dir):
    """Find the last valid observation without reading years of data into memory."""
    filename = Path(data_dir) / _FILENAME
    with _LOCK:
        if not filename.is_file():
            return None
        # The file is append-only; read backwards over at most the last 64 KiB
        # (enough to recover from a truncated final line).
        with open(filename, 'rb') as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            stream.seek(max(0, end - 65536))
            lines = stream.read().decode('utf-8', errors='replace').splitlines()
            for line in reversed(lines):
                try:
                    point = json.loads(line)
                    return {'timestamp': int(point['timestamp']), 'price': point.get('price'),
                            'in_stock': point.get('in_stock'), 'currency': point.get('currency', ''),
                            'status': point.get('status', 'success')}
                except (ValueError, TypeError, KeyError):
                    pass
            return None


def read(data_dir, since=None):
    filename = Path(data_dir) / _FILENAME
    with _LOCK:
        if not filename.is_file():
            return None  # No new-format history yet; caller may show old snapshots.
        result = []
        with open(filename, encoding='utf-8') as stream:
            for line in stream:
                try:
                    point = json.loads(line)
                    ts = int(point['timestamp'])
                    if since is not None and ts < since:
                        continue
                    result.append({'timestamp': ts, 'price': point.get('price'),
                                   'in_stock': point.get('in_stock'),
                                   'currency': point.get('currency', ''),
                                   'status': point.get('status', 'success')})
                except (ValueError, TypeError, KeyError):
                    continue  # Ignore a truncated last line or malformed legacy entry.
        result.sort(key=lambda row: row['timestamp'])
        return result


def clear(data_dir):
    with _LOCK:
        _GENERATIONS[str(data_dir)] += 1
        filename = Path(data_dir) / _FILENAME
        try:
            filename.unlink()
        except FileNotFoundError:
            pass
