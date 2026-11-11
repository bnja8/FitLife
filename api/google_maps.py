import re
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


GOOGLE_MAPS_HOSTS = {
    'goo.gl',
    'google.cl',
    'google.com',
    'maps.app.goo.gl',
    'maps.google.cl',
    'maps.google.com',
    'www.google.cl',
    'www.google.com',
}
COORDINATE_PATTERNS = (
    re.compile(r'@(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)'),
    re.compile(r'!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)'),
    re.compile(r'[?&](?:q|query|ll|center)=(-?\d+(?:\.\d+)?)(?:%2C|,)\s*(-?\d+(?:\.\d+)?)', re.I),
)


def _validate_google_maps_url(url):
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or '').lower()
        port = parsed.port
    except ValueError as error:
        raise ValueError('Pega un enlace válido de Google Maps.') from error
    if (
        parsed.scheme != 'https'
        or hostname not in GOOGLE_MAPS_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
    ):
        raise ValueError('Usa un enlace HTTPS de Google Maps para ubicar la sede.')
    return parsed


def _coordinates_from_url(url):
    decoded = unquote(unquote(url))
    for pattern in COORDINATE_PATTERNS:
        match = pattern.search(decoded)
        if match:
            try:
                latitude, longitude = (Decimal(value) for value in match.groups())
            except InvalidOperation:
                continue
            if (
                latitude.is_finite()
                and longitude.is_finite()
                and Decimal('-90') <= latitude <= Decimal('90')
                and Decimal('-180') <= longitude <= Decimal('180')
            ):
                return latitude, longitude
            raise ValueError('Las coordenadas del enlace están fuera del rango válido.')
    return None


class _GoogleMapsRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        _validate_google_maps_url(new_url)
        return super().redirect_request(request, file, code, message, headers, new_url)


def resolve_google_maps_url(url):
    link = str(url or '').strip()
    if not link or len(link) > 2000:
        raise ValueError('Pega el enlace de Google Maps de la sede.')
    _validate_google_maps_url(link)
    coordinates = _coordinates_from_url(link)
    if coordinates:
        return coordinates
    request = Request(link, headers={
        'User-Agent': 'FitLife location link resolver',
        'Range': 'bytes=0-0',
    })
    try:
        opener = build_opener(_GoogleMapsRedirectHandler)
        with opener.open(request, timeout=8) as response:
            resolved_url = response.geturl()
    except ValueError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise ValueError(
            'No pudimos leer ese enlace. Comprueba que sea un vínculo compartido de Google Maps.'
        ) from error
    coordinates = _coordinates_from_url(resolved_url)
    if not coordinates:
        raise ValueError(
            'El enlace no incluye una ubicación con coordenadas. Comparte un pin o una sede desde Google Maps.'
        )
    return coordinates
