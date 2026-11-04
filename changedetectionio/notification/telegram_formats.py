"""Telegram Rich Message support via Apprise's documented ?template= URL option.

Untrusted template content never becomes a path. Rich payloads are rendered and
validated first, then put into a private temporary JSON file for the duration
of one Apprise notification call.
"""
import json
import os
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def is_telegram(url):
    return urlsplit(url).scheme.lower() == 'tgram'


def add_query(url, **params):
    parsed = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k not in params]
    query.extend((k, v) for k, v in params.items())
    return urlunsplit(parsed._replace(query=urlencode(query)))


def validate_rich_message(raw):
    if not isinstance(raw, str) or len(raw) > 200000:
        raise ValueError('Rich message is missing or exceeds size limit')
    try:
        document = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError('Rich message body must render to valid JSON') from exc
    if not isinstance(document, dict) or not isinstance(document.get('blocks'), list) or not document['blocks']:
        raise ValueError('Rich message requires a non-empty blocks array')
    def visit(blocks, depth=0):
        if depth > 16 or len(blocks) > 500:
            raise ValueError('Rich message exceeds nesting or block limit')
        for block in blocks:
            if not isinstance(block, dict) or not isinstance(block.get('type'), str) or not block['type']:
                raise ValueError('Each Rich Message block requires a type')
            if 'blocks' in block:
                if not isinstance(block['blocks'], list):
                    raise ValueError('Nested Rich Message blocks must be an array')
                visit(block['blocks'], depth+1)
    visit(document['blocks'])
    return document


def private_rich_template(document):
    # Caller must unlink returned path in a finally block.
    handle = tempfile.NamedTemporaryFile(prefix='cd-telegram-rich-', suffix='.json',
                                         mode='w', encoding='utf-8', delete=False)
    try:
        os.chmod(handle.name, 0o600)
        with handle:
            json.dump(document, handle, ensure_ascii=False)
        return handle.name
    except Exception:
        handle.close()
        os.unlink(handle.name)
        raise
