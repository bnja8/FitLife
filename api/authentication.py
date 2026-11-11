import base64
import hashlib
import hmac
import json
import time

from django.conf import settings


TOKEN_LIFETIME_SECONDS = 60 * 60 * 8


def _b64encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _b64decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def issue_token(rut):
    header = _b64encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    payload = _b64encode(json.dumps({
        'sub': str(rut),
        'iat': int(time.time()),
        'exp': int(time.time()) + TOKEN_LIFETIME_SECONDS,
    }, separators=(',', ':')).encode())
    message = f'{header}.{payload}'.encode('ascii')
    signature = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest()
    return f'{header}.{payload}.{_b64encode(signature)}'


def decode_token(token):
    try:
        header, payload, signature = token.split('.')
        message = f'{header}.{payload}'.encode('ascii')
        expected = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64decode(signature)):
            return None
        decoded_header = json.loads(_b64decode(header))
        claims = json.loads(_b64decode(payload))
        if decoded_header != {'alg': 'HS256', 'typ': 'JWT'}:
            return None
        now = int(time.time())
        if int(claims['exp']) <= now or int(claims['iat']) > now + 60:
            return None
        rut = claims['sub']
        return rut if isinstance(rut, str) and rut else None
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
