from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


MAX_ACCOUNT_PASSWORD_LENGTH = 256


def validate_account_password(password, user=None):
    if not isinstance(password, str) or len(password) > MAX_ACCOUNT_PASSWORD_LENGTH:
        raise ValueError('La contraseña supera el largo permitido.')
    try:
        validate_password(password, user=user)
    except ValidationError as error:
        raise ValueError(
            'Usa una contraseña de al menos 12 caracteres, no común ni similar a tus datos.'
        ) from error
