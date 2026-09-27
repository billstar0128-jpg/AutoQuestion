"""Small, bounded browser protocol. No exceptions contain incoming data."""
import json
import re

VERSION = 1
PORT = 37841
MAX_BYTES = 65536


class ProtocolError(ValueError):
    def __init__(self):
        super().__init__('Browser DOM protocol rejected a message.')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError()
        result[key] = value
    return result


def encode_message(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))


def decode_message(raw):
    try:
        if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BYTES:
            raise ProtocolError()
        obj = json.loads(raw, object_pairs_hook=_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError()))
        if not isinstance(obj, dict) or type(obj.get('v')) is not int or obj['v'] != VERSION:
            raise ProtocolError()
        kind = obj.get('type')
        fields = {'v', 'type'}
        if kind == 'hello':
            fields |= {'token'}
            if not isinstance(obj.get('token'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{32}', obj['token']):
                raise ProtocolError()
        elif kind == 'state':
            fields |= {'epoch', 'window', 'tab'}
            for name in ('epoch', 'window', 'tab'):
                if type(obj.get(name)) is not int or not -1 <= obj[name] <= 2**53-1:
                    raise ProtocolError()
            if obj['epoch'] < 0 or (obj['window'] == -1) != (obj['tab'] == -1):
                raise ProtocolError()
        elif kind == 'result':
            fields |= {'request', 'status'}
            if not isinstance(obj.get('request'), str) or not re.fullmatch(r'[a-f0-9]{32}', obj['request']):
                raise ProtocolError()
            if obj.get('status') not in ('ok', 'unavailable', 'changed', 'unchanged'):
                raise ProtocolError()
            if obj['status'] == 'ok':
                fields.add('question')
                q = obj.get('question')
                if (not isinstance(q, dict) or set(q) != {'kind', 'stem', 'options'}
                        or q['kind'] not in ('radio', 'checkbox')
                        or not isinstance(q['stem'], str) or not 1 <= len(q['stem']) <= 8000
                        or not isinstance(q['options'], list) or not 2 <= len(q['options']) <= 50
                        or any(not isinstance(o, str) or not 1 <= len(o) <= 2000 for o in q['options'])):
                    raise ProtocolError()
        elif kind != 'pong':
            raise ProtocolError()
        if set(obj) != fields:
            raise ProtocolError()
        return obj
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        raise ProtocolError() from None
