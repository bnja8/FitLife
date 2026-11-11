import re


_RUT_INPUT = re.compile(r'^[0-9.\s-]+[0-9Kk]$')


def normalize_rut(value):
    """Return a punctuation-free uppercase RUT if its Chilean modulo-11 DV is valid."""
    if not isinstance(value, str):
        raise ValueError('Ingresa un RUT válido.')

    raw = value.strip()
    if not raw or not _RUT_INPUT.fullmatch(raw):
        raise ValueError('Ingresa un RUT válido, por ejemplo 12345678K.')

    normalized = re.sub(r'[.\s-]', '', raw).upper()
    body, supplied_dv = normalized[:-1], normalized[-1]
    if not body.isdigit() or len(body) > 8:
        raise ValueError('Ingresa un RUT válido, por ejemplo 1000005K.')

    total = sum(
        int(digit) * (index % 6 + 2)
        for index, digit in enumerate(reversed(body))
    )
    remainder = 11 - total % 11
    expected_dv = '0' if remainder == 11 else 'K' if remainder == 10 else str(remainder)
    if supplied_dv != expected_dv:
        raise ValueError('El RUT ingresado no es válido. Revisa el número y su dígito verificador.')

    return normalized
