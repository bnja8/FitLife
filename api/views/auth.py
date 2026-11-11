import secrets
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError, IntegrityError, transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..authentication import issue_token
from ..passwords import MAX_ACCOUNT_PASSWORD_LENGTH, validate_account_password
from ..phone import normalize_chilean_phone
from ..person_names import normalize_person_name
from ..rut import normalize_rut
from .common import (
    _database_unavailable, _execute, _json, _json_body, _postgres_constraint_name,
    _profile_ids, _require_persona, _row, _rows,
)


@csrf_exempt
@require_http_methods(['POST'])
def register(request):
    body = _json_body(request)
    if body is None:
        return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)

    raw_names = body.get('nombres', '')
    raw_paternal = body.get('apellido_paterno', '')
    raw_maternal = body.get('apellido_materno', '')
    email = str(body.get('correo', '')).strip().lower()
    password = str(body.get('contrasena', ''))
    raw_document = body.get('rut', body.get('documento_identidad'))
    document = raw_document.strip() or None if isinstance(raw_document, str) else raw_document
    raw_phone = body.get('telefono', '')
    if not all((raw_names, raw_paternal, email, password, document)):
        return _json({'error': 'Completa nombre, RUT, apellido paterno, correo y contraseña.'}, 400)
    try:
        names = normalize_person_name(raw_names, 'nombre')
        paternal = normalize_person_name(raw_paternal, 'apellido paterno')
        maternal = normalize_person_name(raw_maternal, 'apellido materno', required=False) or '-'
    except ValueError as error:
        return _json({'error': str(error)}, 400)
    if len(password) > MAX_ACCOUNT_PASSWORD_LENGTH:
        return _json({'error': 'La contraseña supera el largo permitido.'}, 400)
    if document is not None:
        try:
            document = normalize_rut(document)
        except ValueError as error:
            return _json({'error': str(error)}, 400)
    if len(email) > 254:
        return _json({'error': 'El correo supera el largo permitido.'}, 400)
    try:
        validate_email(email)
    except ValidationError:
        return _json({'error': 'Ingresa un correo electrónico válido.'}, 400)
    try:
        validate_account_password(password, get_user_model()(
            username=document, email=email, first_name=names, last_name=paternal,
        ))
    except ValueError as error:
        return _json({'error': str(error)}, 400)
    try:
        phone = normalize_chilean_phone(raw_phone)
    except ValueError as error:
        return _json({'error': str(error)}, 400)
    if phone and _row('SELECT rut FROM persona WHERE telefono = %s', (phone,)):
        return _json({'error': 'Este número de teléfono ya está asociado a otra cuenta.'}, 409)

    try:
        with transaction.atomic():
            role = _row('SELECT rol_id FROM rol WHERE codigo = %s', ('SOCIO',))
            if role is None:
                return _database_unavailable()
            person = _execute(
                'INSERT INTO persona (rut, nombres, "apellidoPaterno", '
                '"apellidoMaterno", correo, telefono) VALUES (%s, %s, %s, %s, %s, %s) '
                'RETURNING rut',
                (document, names, paternal, maternal, email, phone),
            )
            rut = person[0]
            _execute(
                'INSERT INTO usuario (rut, hash_contrasena) VALUES (%s, %s)',
                (rut, make_password(password)),
            )
            _execute('INSERT INTO usuario_rol (rut, rol_id) VALUES (%s, %s)', (rut, role['rol_id']))
            _execute('INSERT INTO socio (rut) VALUES (%s)', (rut,))
        return _json({
            'token': issue_token(rut),
            'user': {'rut': rut, 'nombres': names, 'roles': ['SOCIO']},
        }, 201)
    except IntegrityError as error:
        if _postgres_constraint_name(error) == 'uq_persona_telefono':
            return _json({'error': 'Este número de teléfono ya está asociado a otra cuenta.'}, 409)
        return _json({'error': 'Ya existe una cuenta con ese correo o RUT.'}, 409)
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def login(request):
    body = _json_body(request)
    if body is None:
        return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
    identifier = str(body.get('identificador', body.get('correo', ''))).strip()
    password = str(body.get('contrasena', ''))
    if not identifier or not password:
        return _json({'error': 'Ingresa correo o RUT y contraseña.'}, 400)
    if len(password) > MAX_ACCOUNT_PASSWORD_LENGTH:
        return _json({'error': 'Correo/RUT o contraseña incorrectos.'}, 401)
    try:
        if '@' in identifier:
            user = _row(
                'SELECT p.rut, p.nombres, u.hash_contrasena FROM persona p '
                'JOIN usuario u ON u.rut = p.rut WHERE LOWER(p.correo) = %s AND u.activo',
                (identifier.lower(),),
            )
        else:
            try:
                rut = normalize_rut(identifier)
            except ValueError:
                rut = None
            user = _row(
                'SELECT p.rut, p.nombres, u.hash_contrasena FROM persona p '
                'JOIN usuario u ON u.rut = p.rut WHERE p.rut = %s AND u.activo',
                (rut,),
            ) if rut else None
        if user is None or not check_password(password, user['hash_contrasena']):
            return _json({'error': 'Correo/RUT o contraseña incorrectos.'}, 401)
        roles = _rows(
            'SELECT r.codigo FROM usuario_rol ur JOIN rol r USING (rol_id) '
            'WHERE ur.rut = %s ORDER BY r.codigo',
            (user['rut'],),
        )
        return _json({
            'token': issue_token(user['rut']),
            'user': {
                'rut': user['rut'],
                'nombres': user['nombres'],
                'roles': [role['codigo'] for role in roles],
            },
        })
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def logout(request):
    return _json({'message': 'Sesión cerrada.'})

@require_http_methods(['GET'])
def me(request):
    try:
        persona, error = _require_persona(request)
        if error:
            return error
        return _json({'user': persona})
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def issue_credential(request):
    try:
        persona, error = _require_persona(request, {'SOCIO', 'INSTRUCTOR'})
        if error:
            return error
        ids = _profile_ids(persona['rut'])
        if 'INSTRUCTOR' in persona['roles'] and ids and ids['instructor_id'] is not None:
            token = secrets.token_urlsafe(32)
            with transaction.atomic():
                active_instructor = _row(
                    'SELECT instructor_id FROM instructor WHERE instructor_id = %s AND activo',
                    (ids['instructor_id'],),
                )
                if active_instructor is None:
                    return _json({'error': 'El perfil profesional no está activo.'}, 409)
                _execute(
                    'UPDATE credencial_personal_qr SET revocada_en = CURRENT_TIMESTAMP '
                    'WHERE instructor_id = %s AND revocada_en IS NULL',
                    (ids['instructor_id'],),
                )
                _execute(
                    "INSERT INTO credencial_personal_qr (instructor_id, hash_token) "
                    "VALUES (%s, public.digest(convert_to(%s, 'UTF8'), 'sha256'))",
                    (ids['instructor_id'], token),
                )
            return _json({'credential': f'FITLIFE-STAFF:{token}'})
        if ids is None or ids['socio_id'] is None:
            return _json({'error': 'La cuenta no tiene un perfil de socio.'}, 409)
        if not _row(
            'SELECT socio_tiene_membresia_vigente(%s) AS vigente',
            (ids['socio_id'],),
        )['vigente']:
            return _json({'error': 'Necesitas una membresía vigente para generar tu credencial.'}, 409)
        token = secrets.token_urlsafe(32)
        with transaction.atomic():
            if not _row(
                'SELECT socio_tiene_membresia_vigente(%s) AS vigente',
                (ids['socio_id'],),
            )['vigente']:
                return _json({'error': 'Necesitas una membresía vigente para generar tu credencial.'}, 409)
            _execute(
                'UPDATE credencial_qr SET revocada_en = CURRENT_TIMESTAMP '
                'WHERE socio_id = %s AND revocada_en IS NULL',
                (ids['socio_id'],),
            )
            _execute(
                "INSERT INTO credencial_qr (socio_id, hash_token) "
                "VALUES (%s, public.digest(convert_to(%s, 'UTF8'), 'sha256'))",
                (ids['socio_id'], token),
            )
        return _json({'credential': token})
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def credential_qr(request):
    try:
        import qrcode
        import qrcode.image.svg

        persona, error = _require_persona(request, {'SOCIO', 'INSTRUCTOR'})
        if error:
            return error
        ids = _profile_ids(persona['rut'])
        if 'INSTRUCTOR' in persona['roles'] and ids and ids['instructor_id'] is not None:
            token = secrets.token_urlsafe(32)
            with transaction.atomic():
                active_instructor = _row(
                    'SELECT instructor_id FROM instructor WHERE instructor_id = %s AND activo',
                    (ids['instructor_id'],),
                )
                if active_instructor is None:
                    return _json({'error': 'El perfil profesional no está activo.'}, 409)
                _execute(
                    'UPDATE credencial_personal_qr SET revocada_en = CURRENT_TIMESTAMP '
                    'WHERE instructor_id = %s AND revocada_en IS NULL',
                    (ids['instructor_id'],),
                )
                _execute(
                    "INSERT INTO credencial_personal_qr (instructor_id, hash_token) "
                    "VALUES (%s, public.digest(convert_to(%s, 'UTF8'), 'sha256'))",
                    (ids['instructor_id'], token),
                )
            qr_token = f'FITLIFE-STAFF:{token}'
        else:
            if ids is None or ids['socio_id'] is None:
                return _json({'error': 'La cuenta no tiene un perfil de socio.'}, 409)
            token = secrets.token_urlsafe(32)
            with transaction.atomic():
                membership = _row(
                    'SELECT membresia_id, plan, fecha_fin, incluye_estacionamiento, otros_beneficios '
                    'FROM vw_membresias WHERE socio_id = %s AND estado_calculado = %s '
                    'ORDER BY fecha_fin DESC LIMIT 1',
                    (ids['socio_id'], 'ACTIVA'),
                )
                if membership is None:
                    return _json({'error': 'Necesitas una membresía vigente para generar tu credencial.'}, 409)
                _execute(
                    'UPDATE credencial_qr SET revocada_en = CURRENT_TIMESTAMP '
                    'WHERE socio_id = %s AND revocada_en IS NULL',
                    (ids['socio_id'],),
                )
                _execute(
                    "INSERT INTO credencial_qr (socio_id, hash_token) "
                    "VALUES (%s, public.digest(convert_to(%s, 'UTF8'), 'sha256'))",
                    (ids['socio_id'], token),
                )
            qr_token = token
        image = qrcode.make(qr_token, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=3)
        output = BytesIO()
        image.save(output)
        response = HttpResponse(output.getvalue(), content_type='image/svg+xml')
        response['Cache-Control'] = 'no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except DatabaseError:
        return _database_unavailable()
    except ImportError:
        return _json({'error': 'La generación de credenciales QR requiere la dependencia qrcode.'}, 503)
