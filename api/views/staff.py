from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError, IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..person_names import normalize_person_name
from ..passwords import validate_account_password
from ..rut import normalize_rut
from .common import _database_unavailable, _execute, _json, _json_body, _require_persona, _row, _rows


def _active_reception_installation(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    if isinstance(value, str) and not value.isdecimal():
        return None
    try:
        installation_id = int(value)
    except ValueError:
        return None
    if installation_id <= 0:
        return None
    if _row(
        'SELECT instalacion_id FROM instalacion WHERE instalacion_id = %s AND activa',
        (installation_id,),
    ) is None:
        return None
    return installation_id


@csrf_exempt
@require_http_methods(['POST'])
def create_staff_user(request):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        raw_names = body.get('nombres', '')
        raw_paternal = body.get('apellido_paterno', '')
        raw_maternal = body.get('apellido_materno', '')
        raw_rut = body.get('rut')
        email = str(body.get('correo', '')).strip().lower()
        password = str(body.get('contrasena', ''))
        role_code = str(body.get('rol', '')).upper()
        profile_type = str(body.get('tipo_profesional', '')).upper()
        specialization = str(body.get('especialidad', '')).strip() or None
        installation_id = body.get('instalacion_id')
        if not raw_names or not raw_paternal or not isinstance(raw_rut, str) or not raw_rut.strip() or not email or not password:
            return _json({'error': 'Completa nombre, RUT, apellido, correo y contraseña.'}, 400)
        try:
            names = normalize_person_name(raw_names, 'nombre')
            paternal = normalize_person_name(raw_paternal, 'apellido paterno')
            maternal = normalize_person_name(raw_maternal, 'apellido materno', required=False) or '-'
        except ValueError as error:
            return _json({'error': str(error)}, 400)
        try:
            rut = normalize_rut(raw_rut)
        except ValueError as error:
            return _json({'error': str(error)}, 400)
        validate_email(email)
        try:
            validate_account_password(password, get_user_model()(
                username=rut, email=email, first_name=names, last_name=paternal,
            ))
        except ValueError as error:
            return _json({'error': str(error)}, 400)
        if role_code not in {'INSTRUCTOR', 'RECEPCIONISTA'}:
            return _json({'error': 'Solo puedes crear cuentas de instructor o recepción desde este formulario.'}, 400)
        if role_code == 'INSTRUCTOR' and profile_type not in {
            'MONITOR', 'PERSONAL_TRAINER', 'COACH', 'PREPARADOR_FISICO',
        }:
            return _json({'error': 'Selecciona el tipo de profesional correspondiente.'}, 400)
        if role_code == 'RECEPCIONISTA':
            installation_id = _active_reception_installation(installation_id)
            if installation_id is None:
                return _json({'error': 'La sede seleccionada no existe o está inactiva.'}, 400)
        with transaction.atomic():
            role = _row('SELECT rol_id FROM rol WHERE codigo = %s', (role_code,))
            if role is None:
                return _json({'error': f'No está configurado el rol {role_code} en la base de datos.'}, 409)
            person = _execute(
                'INSERT INTO persona (rut, nombres, "apellidoPaterno", "apellidoMaterno", correo) '
                'VALUES (%s, %s, %s, %s, %s) RETURNING rut',
                (rut, names, paternal, maternal, email),
            )
            rut = person[0]
            _execute(
                'INSERT INTO usuario (rut, hash_contrasena) VALUES (%s, %s)',
                (rut, make_password(password)),
            )
            _execute('INSERT INTO usuario_rol (rut, rol_id) VALUES (%s, %s)', (rut, role['rol_id']))
            if role_code == 'RECEPCIONISTA':
                _execute(
                    'INSERT INTO recepcionista_sede (rut, instalacion_id) VALUES (%s, %s)',
                    (rut, installation_id),
                )
            if role_code == 'INSTRUCTOR':
                instructor = _execute(
                    'INSERT INTO instructor (rut) VALUES (%s) RETURNING instructor_id',
                    (rut,),
                )
                _execute(
                    'INSERT INTO perfil_instructor (instructor_id, tipo, especialidad) VALUES (%s, %s, %s)',
                    (instructor[0], profile_type, specialization),
                )
        return _json({'rut': rut, 'message': 'Cuenta profesional creada.'}, 201)
    except ValidationError:
        return _json({'error': 'Ingresa un correo electrónico válido.'}, 400)
    except IntegrityError:
        return _json({'error': 'Ya existe una cuenta con ese correo o RUT.'}, 409)
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['PATCH'])
def user_detail(request, rut):
    try:
        persona, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        active = body.get('activo') if body else None
        if not isinstance(active, bool):
            return _json({'error': 'Indica si la cuenta debe quedar activa.'}, 400)
        if rut == persona['rut'] and not active:
            return _json({'error': 'No puedes desactivar tu propia cuenta.'}, 409)
        updated = _execute(
            'UPDATE usuario SET activo = %s WHERE rut = %s RETURNING rut',
            (active, rut),
        )
        if not updated:
            return _json({'error': 'Cuenta no encontrada.'}, 404)
        return _json({'message': 'Estado de la cuenta actualizado.'})
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['PATCH'])
def user_roles(request, rut):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        if set(body) != {'roles', 'tipo_profesional', 'especialidad', 'instalacion_id'}:
            return _json({'error': 'Indica los roles y, si corresponde, el perfil profesional y la sede de recepción.'}, 400)
        requested_roles = body['roles']
        if (
            not isinstance(requested_roles, list)
            or not requested_roles
            or any(not isinstance(role, str) for role in requested_roles)
        ):
            return _json({'error': 'Selecciona al menos un rol válido.'}, 400)
        roles = sorted(set(role.upper() for role in requested_roles))
        allowed_roles = {'SOCIO', 'INSTRUCTOR', 'RECEPCIONISTA', 'ADMINISTRADOR'}
        if set(roles) - allowed_roles:
            return _json({'error': 'Uno o más roles no están permitidos.'}, 400)

        try:
            normalized_rut = normalize_rut(rut)
        except ValueError as error:
            return _json({'error': str(error)}, 400)

        profile_type = str(body.get('tipo_profesional') or '').upper()
        specialization = str(body.get('especialidad') or '').strip() or None
        if 'INSTRUCTOR' in roles and profile_type not in {
            'MONITOR', 'PERSONAL_TRAINER', 'COACH', 'PREPARADOR_FISICO',
        }:
            return _json({'error': 'Selecciona un tipo de perfil profesional válido.'}, 400)
        if specialization and len(specialization) > 150:
            return _json({'error': 'La especialidad no puede superar 150 caracteres.'}, 400)
        installation_id = body['instalacion_id']
        if 'RECEPCIONISTA' in roles:
            installation_id = _active_reception_installation(installation_id)
            if installation_id is None:
                return _json({'error': 'La sede seleccionada no existe o está inactiva.'}, 400)
        else:
            installation_id = None

        with transaction.atomic():
            target = _row(
                'SELECT rut, activo FROM usuario WHERE rut = %s FOR UPDATE',
                (normalized_rut,),
            )
            if target is None:
                return _json({'error': 'Cuenta no encontrada.'}, 404)
            current_roles = {
                row['codigo'] for row in _rows(
                    'SELECT r.codigo FROM usuario_rol ur JOIN rol r USING (rol_id) '
                    'WHERE ur.rut = %s',
                    (normalized_rut,),
                )
            }
            if (
                target['activo']
                and 'ADMINISTRADOR' in current_roles
                and 'ADMINISTRADOR' not in roles
            ):
                active_admins = _row(
                    "SELECT COUNT(*) AS cantidad FROM usuario u "
                    "JOIN usuario_rol ur USING (rut) JOIN rol r USING (rol_id) "
                    "WHERE u.activo AND r.codigo = 'ADMINISTRADOR'"
                )
                if active_admins['cantidad'] <= 1:
                    return _json({'error': 'Debe quedar al menos una cuenta administradora activa.'}, 409)

            role_rows = _rows(
                'SELECT rol_id, codigo FROM rol WHERE codigo = ANY(%s)',
                (roles,),
            )
            if {row['codigo'] for row in role_rows} != set(roles):
                return _json({'error': 'Uno o más roles no están configurados en la base de datos.'}, 409)

            _execute('DELETE FROM usuario_rol WHERE rut = %s', (normalized_rut,))
            for role in role_rows:
                _execute(
                    'INSERT INTO usuario_rol (rut, rol_id) VALUES (%s, %s)',
                    (normalized_rut, role['rol_id']),
                )
            if installation_id is None:
                _execute('DELETE FROM recepcionista_sede WHERE rut = %s', (normalized_rut,))
            else:
                _execute(
                    'INSERT INTO recepcionista_sede (rut, instalacion_id) VALUES (%s, %s) '
                    'ON CONFLICT (rut) DO UPDATE SET instalacion_id = EXCLUDED.instalacion_id',
                    (normalized_rut, installation_id),
                )

            if 'SOCIO' in roles:
                _execute(
                    'INSERT INTO socio (rut, fecha_alta, activo) VALUES (%s, CURRENT_DATE, TRUE) '
                    'ON CONFLICT (rut) DO UPDATE SET activo = TRUE',
                    (normalized_rut,),
                )
            else:
                _execute('UPDATE socio SET activo = FALSE WHERE rut = %s', (normalized_rut,))

            if 'INSTRUCTOR' in roles:
                instructor = _row(
                    'INSERT INTO instructor (rut, activo) VALUES (%s, TRUE) '
                    'ON CONFLICT (rut) DO UPDATE SET activo = TRUE RETURNING instructor_id',
                    (normalized_rut,),
                )
                _execute(
                    'INSERT INTO perfil_instructor (instructor_id, tipo, especialidad, activo) '
                    'VALUES (%s, %s, %s, TRUE) '
                    'ON CONFLICT (instructor_id) DO UPDATE SET tipo = EXCLUDED.tipo, '
                    'especialidad = EXCLUDED.especialidad, activo = TRUE',
                    (instructor['instructor_id'], profile_type, specialization),
                )
            else:
                _execute('UPDATE instructor SET activo = FALSE WHERE rut = %s', (normalized_rut,))

        return _json({'message': 'Los roles y perfiles de la cuenta fueron actualizados.'})
    except IntegrityError:
        return _json({'error': 'No fue posible actualizar los roles y perfiles de la cuenta.'}, 409)
    except DatabaseError:
        return _database_unavailable()
