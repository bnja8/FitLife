import re


_PHONE_CHARACTERS = re.compile(r'^\+?[\d\s().-]+$')


def normalize_chilean_phone(value):
    """Return a Chilean phone number in +56 plus nine-digit format."""
    if not isinstance(value, str):
        raise ValueError('Ingresa un número de teléfono válido.')

    raw = value.strip()
    if not raw:
        return None
    if not _PHONE_CHARACTERS.fullmatch(raw):
        raise ValueError('Ingresa un número de teléfono válido.')

    digits = re.sub(r'\D', '', raw)
    if len(digits) == 11 and digits.startswith('56'):
        digits = digits[2:]
    if len(digits) != 9:
        raise ValueError('Ingresa los 9 dígitos de tu número de teléfono.')
    return f'+56{digits}'
