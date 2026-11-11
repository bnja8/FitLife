import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..google_maps import resolve_google_maps_url
from ..locations import REGION_CITIES, valid_region_city
from ..person_names import normalize_person_name
from ..passwords import validate_account_password
from ..phone import normalize_chilean_phone
from ..rut import normalize_rut
from .common import (
    _database_unavailable, _execute, _json, _json_body, _postgres_constraint_name, _postgres_error_code,
    _require_persona, _row, _rows,
)

from .admin_entities import ENTITIES, FOREIGN_OPTIONS


def _entity_or_error(name):
    return ENTITIES.get(name)


def _field_value(kind, value):
    if value == '' or value is None:
        return None
    if kind in {'fk:personas', 'fk:cuentas'}:
        return normalize_rut(value)
    if kind.startswith('fk:') or kind == 'int':
        number = int(value)
        if kind.startswith('fk:') and number < 1:
            raise ValueError('Los identificadores deben ser positivos.')
        if kind == 'int' and number < 0:
            raise ValueError('El valor no puede ser negativo.')
        return number
    if kind == 'bool':
        if isinstance(value, bool):
            return value
        if str(value).lower() not in {'true', 'false'}:
            raise ValueError('Indica un valor verdadero o falso.')
        return str(value).lower() == 'true'
    if kind == 'phone':
        return normalize_chilean_phone(value if isinstance(value, str) else str(value))
    if kind == 'person_name':
        return normalize_person_name(value)
    if kind in {'decimal', 'latitude', 'longitude'}:
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError('El valor numérico no es válido.')
        return number
    if kind == 'date':
        return date.fromisoformat(str(value))
    if kind == 'datetime':
        parsed = parse_datetime(str(value))
        if parsed is None:
            raise ValueError('La fecha y hora no son válidas.')
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
    if kind == 'textarea' and value is None:
        return None
    return str(value).strip()


def _entity_payload(entity):
    return {
        'entities': [
            {'key': key, 'label': config['label']}
            for key, config in ENTITIES.items()
        ],
        'entity': entity,
    }


def _entity_records(config):
    if config.get('special') == 'professional-assignment':
        return _rows(
            'SELECT asignacion.instructor_id, asignacion.socio_id, '
            'profesional.nombres || %s || profesional."apellidoPaterno" AS profesional, '
            'socio.nombres || %s || socio."apellidoPaterno" AS socio, '
            "CONCAT(asignacion.instructor_id, '-', asignacion.socio_id) AS record_key "
            'FROM instructor_socio asignacion '
            'JOIN instructor i USING (instructor_id) JOIN persona profesional ON profesional.rut = i.rut '
            'JOIN socio s USING (socio_id) JOIN persona socio ON socio.rut = s.rut '
            'WHERE asignacion.activo '
            'ORDER BY profesional, socio LIMIT 500',
            (' ', ' '),
        )
    if config.get('special') == 'reservation':
        return _rows(
            "SELECT r.reserva_id, r.sesion_id, r.socio_id, r.estado, r.creada_en "
            "FROM reserva r JOIN sesion_clase sc USING (sesion_id) "
            "WHERE sc.inicio > CURRENT_TIMESTAMP AND r.estado IN ('RESERVADA', 'EN_ESPERA') "
            "ORDER BY sc.inicio LIMIT 500"
        )
    if config.get('special') == 'credential':
        return _rows(
            'SELECT credencial_id, socio_id, emitida_en, expira_en, revocada_en '
            'FROM credencial_qr WHERE revocada_en IS NULL ORDER BY emitida_en DESC LIMIT 500'
        )
    if config.get('special') == 'membership':
        return _rows(
            'SELECT membresia_id, socio, plan, estado_calculado, fecha_inicio, fecha_fin, '
            'precio_acordado, incluye_entrenador_personal, incluye_lockers, otros_beneficios, '
            'incluye_estacionamiento, sede FROM vw_membresias '
            'ORDER BY fecha_inicio DESC NULLS LAST, '
            'membresia_id DESC LIMIT 500'
        )
    if config.get('special') == 'role-assignment':
        return _rows(
            "SELECT ur.rut, ur.rol_id, "
            "CONCAT(ur.rut, '-', ur.rol_id) AS record_key "
            "FROM usuario_rol ur ORDER BY ur.rut, ur.rol_id LIMIT 500"
        )
    where = f" WHERE {config['active_only']}" if config.get('active_only') else ''
    columns = [
        "CASE WHEN latitud IS NOT NULL AND longitud IS NOT NULL "
        "THEN CONCAT('https://maps.google.com/?q=', latitud, ',', longitud) END AS mapa_url"
        if config['table'] == 'instalacion' and column == 'mapa_url' else column
        for column in config['columns']
    ]
    query = f"SELECT {', '.join(columns)} FROM {config['table']}{where} ORDER BY {config['order']} LIMIT 500"
    return _rows(query)


def _options_for_field(kind):
    if not kind.startswith('fk:'):
        return []
    query, params = FOREIGN_OPTIONS[kind[3:]]
    return _rows(query, params)


def _entity_fields(config):
    fields = []
    for name, label, kind, required, extra in config['fields']:
        field = {
            'name': name,
            'label': label,
            'type': kind.split(':')[0] if kind.startswith('fk:') else kind,
            'required': required,
            'choices': extra if kind == 'choice' else list(REGION_CITIES) if kind == 'region' else [],
            'options': _options_for_field(kind),
        }
        if kind == 'latitude':
            field.update(min=-90, max=90, step='0.000001')
        elif kind == 'longitude':
            field.update(min=-180, max=180, step='0.000001')
        fields.append(field)
    return fields


def _validate_entity_values(config, body, creating):
    values = {}
    definitions = {field[0]: field for field in config['fields']}
    unknown = set(body) - definitions.keys()
    if unknown:
        raise ValueError('La solicitud contiene campos que no se pueden modificar.')
    if not creating and set(body).intersection(config.get('immutable_fields', [])):
        raise ValueError('No se puede cambiar el identificador de la cuenta.')
    for name, (field_name, label, kind, required, extra) in definitions.items():
        if name not in body:
            if creating and required:
                raise ValueError(f'El campo {label} es obligatorio.')
            continue
        raw_value = body[name]
        if kind == 'password':
            password = str(raw_value or '')
            if not password and not creating:
                continue
            validate_account_password(password)
            values[name] = make_password(password)
            continue
        if required and (raw_value is None or raw_value == ''):
            raise ValueError(f'El campo {label} es obligatorio.')
        if kind == 'choice' and raw_value not in extra:
            raise ValueError(f'El valor de {label} no es válido.')
        if kind == 'google_maps_url':
            latitude, longitude = resolve_google_maps_url(raw_value)
            values['latitud'] = latitude
            values['longitud'] = longitude
            continue
        try:
            if config['table'] == 'persona' and name == 'rut':
                values[name] = normalize_rut(raw_value)
            elif config['table'] == 'persona' and name == 'apellidoMaterno':
                values[name] = normalize_person_name(
                    raw_value, 'apellido materno', required=False,
                ) or '-'
            elif config['table'] == 'plan_membresia' and name == 'otros_beneficios':
                values[name] = str(raw_value or '').strip()
            else:
                values[name] = _field_value(kind, raw_value)
        except (ValueError, TypeError, InvalidOperation) as error:
            raise ValueError(f'Revisa el campo {label}.') from error
        if values[name] is None and required:
            raise ValueError(f'El campo {label} es obligatorio.')
    if creating and config.get('password_required') and not values.get(config['password_field']):
        raise ValueError('La contraseña inicial es obligatoria.')
    if 'correo' in values:
        if len(values['correo']) > 254:
            raise ValueError('El correo supera el largo permitido.')
        try:
            validate_email(values['correo'])
        except ValidationError as error:
            raise ValueError('Ingresa un correo electrónico válido.') from error
        values['correo'] = values['correo'].lower()
    if 'codigo' in values:
        values['codigo'] = values['codigo'].upper()
    if config['table'] == 'sesion_clase' and 'inicio' in values and values['inicio'] <= timezone.now():
        raise ValueError('La fecha de inicio de la clase debe estar en el futuro.')
    if config['table'] == 'sesion_clase' and {'inicio', 'fin'}.issubset(values) and values['fin'] <= values['inicio']:
        raise ValueError('La fecha de término debe ser posterior al inicio.')
    if config['table'] == 'instalacion' and {'tiene_lockers', 'cantidad_lockers'}.intersection(values):
        if not {'tiene_lockers', 'cantidad_lockers'}.issubset(values):
            raise ValueError('Actualiza conjuntamente si la sede cuenta con lockers y su cantidad.')
        has_lockers = values['tiene_lockers']
        locker_count = values['cantidad_lockers']
        if has_lockers is False and locker_count != 0:
            raise ValueError('La cantidad de lockers debe ser cero si la sede no cuenta con lockers.')
        if has_lockers is True and locker_count < 1:
            raise ValueError('La sede debe tener al menos un locker.')
    if config['table'] == 'instalacion' and {
        'tiene_estacionamiento', 'cupos_estacionamiento',
    }.intersection(values):
        if not {'tiene_estacionamiento', 'cupos_estacionamiento'}.issubset(values):
            raise ValueError('Actualiza conjuntamente si la sede cuenta con estacionamiento y su cupo.')
        has_parking = values['tiene_estacionamiento']
        parking_capacity = values['cupos_estacionamiento']
        if has_parking is False and parking_capacity != 0:
            raise ValueError('Los cupos deben ser cero si la sede no cuenta con estacionamiento.')
        if has_parking is True and parking_capacity < 1:
            raise ValueError('La sede debe tener al menos un cupo de estacionamiento.')
    for service, quantity, label in (
        ('tiene_vestidores', 'cantidad_vestidores', 'vestidores'),
        ('tiene_duchas', 'cantidad_duchas', 'duchas'),
    ):
        if config['table'] == 'instalacion' and {service, quantity}.intersection(values):
            if not {service, quantity}.issubset(values):
                raise ValueError(f'Actualiza conjuntamente si la sede cuenta con {label} y su cantidad.')
            if values[service] is False and values[quantity] != 0:
                raise ValueError(f'La cantidad debe ser cero si la sede no cuenta con {label}.')
            if values[service] is True and values[quantity] < 1:
                raise ValueError(f'La sede debe tener al menos un elemento de {label}.')
    if config['table'] == 'instalacion':
        if {'region', 'ciudad'}.intersection(values):
            if not valid_region_city(values.get('region'), values.get('ciudad')):
                raise ValueError('Selecciona una región y una ciudad o comuna válidas.')
        if any(len(str(values.get(field, '') or '')) > 100 for field in (
            'horario_lunes_viernes', 'horario_sabados_dom_festivos',
        )):
            raise ValueError('El horario no puede superar los 100 caracteres.')
        if len(str(values.get('caracteristicas', '') or '')) > 3000:
            raise ValueError('Las características superan el largo permitido.')
        if {'latitud', 'longitud'}.intersection(values):
            if not {'latitud', 'longitud'}.issubset(values):
                raise ValueError('Actualiza conjuntamente la latitud y la longitud de la sede.')
            if not Decimal('-90') <= values['latitud'] <= Decimal('90') \
                    or not Decimal('-180') <= values['longitud'] <= Decimal('180'):
                raise ValueError('Las coordenadas están fuera del rango válido.')
        image_url = values.get('imagen_url')
        if image_url:
            parsed_image_url = urlsplit(image_url)
            if len(image_url) > 500 or (
                parsed_image_url.scheme not in {'http', 'https'}
                and not image_url.startswith(('/media/', '/static/'))
            ) or (parsed_image_url.scheme in {'http', 'https'} and not parsed_image_url.netloc):
                raise ValueError('La imagen debe ser una URL HTTP/HTTPS o una ruta local /media/ o /static/.')
    return values


def _column_expression(config, name):
    column = config.get('columns_map', {}).get(name, name)
    if column in {'apellidoPaterno', 'apellidoMaterno'}:
        return f'"{column}"'
    return column


def _insert_entity(config, values):
    if config.get('special') == 'professional-assignment':
        row = _execute(
            'INSERT INTO instructor_socio (instructor_id, socio_id, asignada_por) '
            'VALUES (%s, %s, %s) ON CONFLICT (instructor_id, socio_id) '
            'DO UPDATE SET asignada_por = EXCLUDED.asignada_por, '
            'asignada_en = CURRENT_TIMESTAMP, activo = TRUE RETURNING instructor_id',
            (values['instructor_id'], values['socio_id'], values['asignada_por']),
        )
        return row[0]
    columns = list(values)
    placeholders = []
    params = []
    for name in columns:
        cast = config.get('casts', {}).get(name)
        placeholders.append(f'%s::{cast}' if cast else '%s')
        params.append(values[name])
    returning = config['pk']
    row = _execute(
        f"INSERT INTO {config['table']} ({', '.join(_column_expression(config, name) for name in columns)}) "
        f"VALUES ({', '.join(placeholders)}) RETURNING {returning}",
        params,
    )
    return row[0]


def _update_entity(config, record_id, values):
    assignments = []
    params = []
    for name, value in values.items():
        cast = config.get('casts', {}).get(name)
        assignments.append(f"{_column_expression(config, name)} = %s::{cast}" if cast
                           else f"{_column_expression(config, name)} = %s")
        params.append(value)
    if not assignments:
        return False
    params.append(record_id)
    where = f"{config['pk']} = %s"
    if config.get('active_only'):
        where += f" AND {config['active_only']}"
    result = _execute(
        f"UPDATE {config['table']} SET {', '.join(assignments)} "
        f"WHERE {where} RETURNING {config['pk']}",
        params,
    )
    return result is not None


def _record_id_value(config, record_id):
    if config['table'] in {'persona', 'usuario', 'prueba_socio'}:
        return normalize_rut(record_id)
    return int(record_id)


def _delete_entity(config, record_id):
    if config.get('special') == 'professional-assignment':
        try:
            instructor_id, member_id = (int(value) for value in record_id.split('-', maxsplit=1))
        except (AttributeError, TypeError, ValueError):
            raise ValueError('El identificador de asignación no es válido.')
        if instructor_id < 1 or member_id < 1:
            raise ValueError('El identificador de asignación no es válido.')
        result = _execute(
            'UPDATE instructor_socio SET activo = FALSE '
            'WHERE instructor_id = %s AND socio_id = %s AND activo '
            'RETURNING instructor_id',
            (instructor_id, member_id),
        )
        return result is not None
    if config.get('special') == 'role-assignment':
        try:
            person_rut, role_id = record_id.rsplit('-', maxsplit=1)
            role_id = int(role_id)
        except (AttributeError, ValueError):
            raise ValueError('El identificador de asignación de rol no es válido.')
        result = _execute(
            'DELETE FROM usuario_rol WHERE rut = %s AND rol_id = %s RETURNING rut',
            (person_rut, role_id),
        )
        return result is not None
    soft_delete = config.get('soft_delete')
    if soft_delete:
        column, value = soft_delete
        result = _execute(
            f"UPDATE {config['table']} SET {column} = %s WHERE {config['pk']} = %s RETURNING {config['pk']}",
            (value, record_id),
        )
    elif config['table'] == 'membresia':
        result = _execute(
            "UPDATE membresia SET estado = 'CANCELADA', "
            "fecha_inicio = COALESCE(fecha_inicio, CURRENT_DATE), "
            "fecha_fin = COALESCE(fecha_fin, CURRENT_DATE) WHERE membresia_id = %s "
            "AND estado <> 'CANCELADA' RETURNING membresia_id",
            (record_id,),
        )
    elif config['table'] == 'sesion_clase':
        result = _execute(
            'SELECT cancelar_sesion_clase(%s)', (record_id,),
        )
    else:
        result = _execute(
            f"DELETE FROM {config['table']} WHERE {config['pk']} = %s RETURNING {config['pk']}",
            (record_id,),
        )
    return result is not None


@csrf_exempt
@require_http_methods(['GET', 'POST', 'PATCH', 'DELETE'])
def admin_data(request, entity=None, record_id=None):
    try:
        persona, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error

        if request.method == 'GET' and entity is None:
            return _json(_entity_payload(None))

        config = _entity_or_error(entity)
        if config is None:
            return _json({'error': 'La tabla solicitada no está disponible para administración.'}, 404)

        if request.method == 'GET':
            return _json({
                'entity': entity,
                'label': config['label'],
                'fields': _entity_fields(config),
                **({'location_options': REGION_CITIES} if config['table'] == 'instalacion' else {}),
                'records': _entity_records(config),
                'special': config.get('special'),
                'primary_key': config['pk'],
                'delete_label': (
                    'Revocar' if config.get('special') == 'credential'
                    else 'Cancelar' if config.get('special') == 'reservation'
                    or config['table'] in {'membresia', 'sesion_clase'}
                    else 'Desasignar' if config.get('special') == 'professional-assignment'
                    else 'Desactivar' if config.get('soft_delete')
                    else 'Eliminar'
                ),
                'column_labels': {
                    **config.get('column_labels', {}),
                    **{field[0]: field[1] for field in config['fields']},
                },
            })

        if config.get('special') == 'membership':
            return _json({
                'error': 'Las membresías solo se pueden consultar; no se permite asignarlas ni modificarlas manualmente.',
            }, 405)

        if config.get('special') == 'credential':
            return _credential_operation(request, config, record_id)
        if config.get('special') == 'reservation':
            return _reservation_operation(request, config, record_id)
        if config.get('special') == 'role-assignment' and request.method == 'PATCH':
            return _json({'error': 'Las asignaciones de rol se crean o eliminan.'}, 405)
        if config.get('special') == 'professional-assignment' and request.method == 'PATCH':
            return _json({'error': 'Las asignaciones profesional-socio se crean o eliminan.'}, 405)

        if request.method == 'DELETE':
            with transaction.atomic():
                if config.get('special') == 'role-assignment':
                    try:
                        person_rut, role_id = record_id.rsplit('-', maxsplit=1)
                        person_rut = normalize_rut(person_rut)
                        role_id = int(role_id)
                    except (AttributeError, ValueError):
                        return _json({'error': 'El identificador de asignación de rol no es válido.'}, 400)
                    target_id = record_id
                    assignment = _row(
                        'SELECT 1 AS existe FROM usuario_rol ur JOIN rol r USING (rol_id) '
                        'WHERE ur.rut = %s AND ur.rol_id = %s AND r.codigo = %s',
                        (person_rut, role_id, 'ADMINISTRADOR'),
                    )
                    if assignment and person_rut == persona['rut']:
                        return _json({'error': 'No puedes quitarte tu propio rol de administrador.'}, 409)
                    if assignment:
                        active_admins = _rows(
                            'SELECT u.rut FROM usuario u '
                            'JOIN usuario_rol ur USING (rut) '
                            'JOIN rol r USING (rol_id) '
                            "WHERE u.activo AND r.codigo = 'ADMINISTRADOR' "
                            'ORDER BY u.rut '
                            'FOR UPDATE OF u'
                        )
                        if len(active_admins) <= 1:
                            return _json({'error': 'Debe quedar al menos una cuenta administradora activa.'}, 409)
                elif config.get('special') == 'professional-assignment':
                    target_id = record_id
                else:
                    try:
                        numeric_id = _record_id_value(config, record_id)
                    except (TypeError, ValueError):
                        return _json({'error': 'El identificador no es válido.'}, 400)
                    if config['table'] == 'usuario' and numeric_id == persona['rut']:
                        return _json({'error': 'No puedes desactivar tu propia cuenta.'}, 409)
                    if config['table'] == 'rol':
                        role = _row('SELECT codigo FROM rol WHERE rol_id = %s', (numeric_id,))
                        if role and role['codigo'] in SYSTEM_ROLES:
                            return _json({'error': 'Los roles principales del sistema no se pueden eliminar.'}, 409)
                    target_id = numeric_id
                if not _delete_entity(config, target_id):
                    return _json({'error': 'No se encontró el registro o ya fue desactivado.'}, 404)
            return _json({'message': f"{config['label']} actualizado."})

        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        if (
            request.method == 'PATCH'
            and 'rut' in body
            and 'rut' in config.get('immutable_fields', [])
        ):
            try:
                submitted_rut = normalize_rut(body['rut'])
                record_rut = normalize_rut(record_id)
            except ValueError:
                pass
            else:
                if submitted_rut == record_rut:
                    body.pop('rut')
        values = _validate_entity_values(config, body, request.method == 'POST')
        if config.get('special') == 'professional-assignment':
            if request.method != 'POST':
                return _json({'error': 'Las asignaciones profesional-socio se crean o eliminan.'}, 405)
            valid_instructor = _row(
                "SELECT 1 AS permitido FROM instructor i "
                "JOIN perfil_instructor pi USING (instructor_id) "
                "WHERE i.instructor_id = %s AND i.activo AND pi.activo "
                "AND pi.tipo IN ('PERSONAL_TRAINER', 'COACH', 'PREPARADOR_FISICO')",
                (values['instructor_id'],),
            )
            valid_member = _row(
                'SELECT 1 AS permitido FROM socio WHERE socio_id = %s AND activo',
                (values['socio_id'],),
            )
            if not valid_instructor:
                return _json({'error': 'Selecciona un Entrenador personal, Coach o Preparador físico activo.'}, 400)
            if not valid_member:
                return _json({'error': 'Selecciona un socio activo.'}, 400)
            values['asignada_por'] = persona['rut']
        with transaction.atomic():
            if request.method == 'POST':
                record_key = _insert_entity(config, values)
                return _json({'id': record_key, 'message': f"{config['label']} creado."}, 201)
            try:
                numeric_id = _record_id_value(config, record_id)
            except (TypeError, ValueError):
                return _json({'error': 'El identificador no es válido.'}, 400)
            if config['table'] == 'rol' and 'codigo' in values:
                role = _row('SELECT codigo FROM rol WHERE rol_id = %s', (numeric_id,))
                if role and role['codigo'] in SYSTEM_ROLES and values['codigo'] != role['codigo']:
                    return _json({'error': 'No se puede cambiar el código de un rol principal.'}, 409)
            if config['table'] == 'usuario' and numeric_id == persona['rut'] and values.get('activo') is False:
                return _json({'error': 'No puedes desactivar tu propia cuenta.'}, 409)
            cancelled_session = config['table'] == 'sesion_clase' and values.get('estado') == 'CANCELADA'
            if cancelled_session:
                _execute('SELECT cancelar_sesion_clase(%s)', (numeric_id,))
                values.pop('estado')
            if values and not _update_entity(config, numeric_id, values):
                return _json({'error': 'No se encontró el registro o no hay cambios.'}, 404)
            if not values and not cancelled_session:
                return _json({'error': 'No se encontró el registro o no hay cambios.'}, 404)
        return _json({'message': f"{config['label']} actualizado."})
    except ValueError as error:
        return _json({'error': str(error)}, 400)
    except IntegrityError as error:
        if _postgres_constraint_name(error) == 'uq_persona_telefono':
            return _json({'error': 'Este número de teléfono ya está asociado a otra persona.'}, 409)
        return _json({'error': 'No se pudo guardar: revisa duplicados, relaciones y reglas del registro.'}, 409)
    except DatabaseError as error:
        if _postgres_error_code(error) == 'P0001':
            return _json({'error': 'La operación no es válida para el estado actual del registro.'}, 409)
        return _database_unavailable()


def _credential_operation(request, config, record_id):
    if request.method == 'POST':
        body = _json_body(request)
        try:
            member_id = int(body.get('socio_id')) if body else 0
        except (ValueError, TypeError):
            return _json({'error': 'Selecciona un socio válido.'}, 400)
        if member_id < 1:
            return _json({'error': 'Selecciona un socio válido.'}, 400)
        token = secrets.token_urlsafe(32)
        expiration = body.get('expira_en') or None
        if expiration:
            try:
                expiration = _field_value('datetime', expiration)
            except ValueError as error:
                return _json({'error': 'La fecha de expiración no es válida.'}, 400)
        with transaction.atomic():
            active_membership = _row(
                'SELECT socio_tiene_membresia_vigente(%s) AS vigente',
                (member_id,),
            )
            if active_membership is None or not active_membership['vigente']:
                return _json({
                    'error': 'El socio necesita una membresía vigente para emitir una credencial QR.',
                }, 409)
            _execute(
                'UPDATE credencial_qr SET revocada_en = CURRENT_TIMESTAMP '
                'WHERE socio_id = %s AND revocada_en IS NULL',
                (member_id,),
            )
            credential = _execute(
                "INSERT INTO credencial_qr (socio_id, hash_token, expira_en) "
                "VALUES (%s, public.digest(convert_to(%s, 'UTF8'), 'sha256'), %s) "
                "RETURNING credencial_id",
                (member_id, token, expiration),
            )
        response = _json({
            'id': credential[0],
            'credential': token,
            'message': 'Credencial creada. El token solo se muestra esta vez.',
        }, 201)
        response['Cache-Control'] = 'no-store'
        response['Pragma'] = 'no-cache'
        return response
    if request.method == 'DELETE':
        try:
            credential_id = int(record_id)
        except (ValueError, TypeError):
            return _json({'error': 'El identificador no es válido.'}, 400)
        result = _execute(
            'UPDATE credencial_qr SET revocada_en = CURRENT_TIMESTAMP '
            'WHERE credencial_id = %s AND revocada_en IS NULL RETURNING credencial_id',
            (credential_id,),
        )
        if result is None:
            return _json({'error': 'Credencial no encontrada o ya revocada.'}, 404)
        return _json({'message': 'Credencial revocada.'})
    return _json({'error': 'La operación no está disponible para credenciales QR.'}, 405)


def _reservation_operation(request, config, record_id):
    if request.method == 'POST':
        body = _json_body(request)
        try:
            session_id = int(body.get('sesion_id')) if body else 0
            member_id = int(body.get('socio_id')) if body else 0
        except (ValueError, TypeError):
            return _json({'error': 'Selecciona una clase y un socio válidos.'}, 400)
        if session_id < 1 or member_id < 1:
            return _json({'error': 'Selecciona una clase y un socio válidos.'}, 400)
        with transaction.atomic():
            session = _row('SELECT precio FROM sesion_clase WHERE sesion_id = %s', (session_id,))
            if session is None:
                return _json({'error': 'La clase seleccionada no existe.'}, 404)
            result = _execute('SELECT * FROM reservar_clase(%s, %s)', (session_id, member_id))
            payment_pending = session['precio'] > 0
            if payment_pending:
                _execute(
                    "INSERT INTO pago_reserva (reserva_id, metodo, estado, monto) "
                    "VALUES (%s, 'OTRO'::metodo_pago, 'PENDIENTE', %s)",
                    (result[0], session['precio']),
                )
        return _json({
            'id': result[0],
            'estado': result[1],
            'pago_pendiente': payment_pending,
            'message': 'Reserva registrada.',
        }, 201)
    if request.method == 'DELETE':
        try:
            reservation_id = int(record_id)
        except (ValueError, TypeError):
            return _json({'error': 'El identificador no es válido.'}, 400)
        result = _execute(
            'SELECT cancelar_reserva(%s, (SELECT socio_id FROM reserva WHERE reserva_id = %s))',
            (reservation_id, reservation_id),
        )
        return _json({'message': 'Reserva cancelada.', 'personas_promovidas': result[0]})
    return _json({'error': 'Las reservas solo pueden crearse o cancelarse.'}, 405)
