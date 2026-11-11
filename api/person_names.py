import re
import unicodedata


_PERSON_NAME = re.compile(r'^[^\W\d_]+(?: [^\W\d_]+)*$', re.UNICODE)


def normalize_person_name(value, label='nombre', required=True, max_length=100):
    if not isinstance(value, str):
        raise ValueError(f'Ingresa un {label} válido.')

    normalized = ' '.join(unicodedata.normalize('NFC', value).split())
    if not normalized:
        if required:
            raise ValueError(f'Ingresa un {label}.')
        return None

    if len(normalized) > max_length or not _PERSON_NAME.fullmatch(normalized):
        raise ValueError(f'El {label} solo puede contener letras y espacios.')
    if sum(character.isalpha() for character in normalized) < 3:
        raise ValueError(f'El {label} debe tener al menos 3 letras.')
    return normalized
