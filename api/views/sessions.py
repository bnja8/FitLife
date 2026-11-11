from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .common import (
    _database_unavailable, _delete_class_image, _execute, _json, _json_body,
    _postgres_error_code, _profile_ids, _require_persona, _row, _rows, _store_class_image,
)


def _class_assignment_exists(installation_id, instructor_id, room_id):
    return _row(
        'SELECT 1 AS permitido FROM instalacion i '
        'JOIN sala sa ON sa.instalacion_id = i.instalacion_id '
        'JOIN instalacion_instructor ii ON ii.instalacion_id = i.instalacion_id '
        'JOIN instructor ins ON ins.instructor_id = ii.instructor_id '
        'WHERE i.instalacion_id = %s AND i.activa AND sa.sala_id = %s AND sa.activa '
        'AND ii.instructor_id = %s AND ins.activo',
        (installation_id, room_id, instructor_id),
    ) is not None


@require_http_methods(['GET'])
def public_sessions(request):
    try:
        sessions = _rows(
            "SELECT sc.sesion_id, COALESCE(sc.nombre_sesion, a.nombre) AS nombre, "
            "a.nombre AS actividad, v.instructor, v.sala, sc.inicio, sc.fin, sc.estado, "
            "v.cupos_disponibles, sc.precio, sc.imagen_url "
            "FROM sesion_clase sc "
            "JOIN actividad a USING (actividad_id) "
            "JOIN vw_disponibilidad_clases v USING (sesion_id) "
            "WHERE sc.estado = 'PROGRAMADA' AND a.activa "
            "AND sc.inicio >= CURRENT_TIMESTAMP "
            "ORDER BY sc.inicio ASC LIMIT 6"
        )
        return _json({'sessions': sessions})
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def sessions(request):
    try:
        persona, error = _require_persona(request)
        if error:
            return error
        if request.method == 'GET':
            activity_id = request.GET.get('actividad')
            day = request.GET.get('fecha')
            query = (
                "SELECT sc.sesion_id, COALESCE(sc.nombre_sesion, a.nombre) AS nombre, "
                "a.nombre AS actividad, v.instructor, v.sala, sc.inicio, sc.fin, sc.estado, "
                "sc.actividad_id, sc.instructor_id, sc.sala_id, "
                "(SELECT instalacion_id FROM sala WHERE sala_id = sc.sala_id) AS instalacion_id, "
                "sc.cupos_totales, v.cupos_ocupados, v.cupos_disponibles, "
                "v.personas_en_espera, sc.precio, sc.imagen_url FROM sesion_clase sc "
                "JOIN actividad a USING (actividad_id) "
                "JOIN vw_disponibilidad_clases v USING (sesion_id) "
                "WHERE sc.estado = 'PROGRAMADA' AND sc.inicio > CURRENT_TIMESTAMP"
            )
            params = []
            if activity_id:
                query += ' AND sc.actividad_id = %s'
                params.append(activity_id)
            if day:
                try:
                    selected_day = date.fromisoformat(day)
                except ValueError:
                    return _json({'error': 'La fecha indicada no es válida.'}, 400)
                query += ' AND sc.inicio::date = %s'
                params.append(selected_day)
            query += ' ORDER BY sc.inicio LIMIT 100'
            return _json({'sessions': _rows(query, params)})

        is_admin = 'ADMINISTRADOR' in persona['roles']
        instructor_id = None
        if not is_admin:
            if 'INSTRUCTOR' not in persona['roles']:
                return _json({'error': 'Solo Administración o un Monitor puede programar clases.'}, 403)
            ids = _profile_ids(persona['rut'])
            instructor_id = ids['instructor_id'] if ids else None
            profile = _row(
                'SELECT tipo FROM perfil_instructor WHERE instructor_id = %s AND activo',
                (instructor_id,),
            ) if instructor_id else None
            if not profile or profile['tipo'] != 'MONITOR':
                return _json({'error': 'La planificación de clases grupales corresponde a Monitor.'}, 403)
        body = request.POST if request.content_type.startswith('multipart/form-data') else _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud no es válido.'}, 400)
        activity_name = str(body.get('actividad', '')).strip()
        name = str(body.get('nombre', '')).strip() or activity_name
        start = parse_datetime(str(body.get('inicio', '')))
        end = parse_datetime(str(body.get('fin', '')))
        if start and timezone.is_naive(start):
            start = timezone.make_aware(start)
        if end and timezone.is_naive(end):
            end = timezone.make_aware(end)
        try:
            installation_id = int(body.get('instalacion_id'))
            if is_admin:
                instructor_id = int(body.get('instructor_id'))
            room_id = int(body.get('sala_id'))
            capacity = int(body.get('cupos_totales'))
            price = Decimal(str(body.get('precio', 0)))
        except (ValueError, TypeError, InvalidOperation):
            return _json({'error': 'Selecciona sede, instructor y sala; revisa también cupos y precio.'}, 400)
        if (not activity_name or not start or not end or end <= start or capacity < 1
                or installation_id < 1 or instructor_id < 1 or room_id < 1
                or not price.is_finite() or price < 0 or start <= timezone.now()):
            return _json({'error': 'Completa actividad, horario válido, cupos y precio no negativo.'}, 400)
        if not is_admin and not _row(
            'SELECT 1 AS asignada FROM instalacion_instructor '
            'WHERE instalacion_id = %s AND instructor_id = %s',
            (installation_id, instructor_id),
        ):
            return _json({'error': 'Solo puedes programar clases en sedes asignadas a tu perfil.'}, 403)
        if not _class_assignment_exists(installation_id, instructor_id, room_id):
            return _json({'error': 'El instructor y la sala deben pertenecer a la sede seleccionada.'}, 400)
        description = str(body.get('descripcion_sesion', '')).strip()
        observations = str(body.get('observaciones', '')).strip()
        intensity = body.get('intensidad') or None
        if len(description) > 3000 or len(observations) > 3000:
            return _json({'error': 'La descripción y las observaciones no pueden superar 3000 caracteres.'}, 400)
        if intensity not in {None, 'BAJA', 'MODERADA', 'ALTA'}:
            return _json({'error': 'Selecciona una intensidad válida para la clase.'}, 400)
        try:
            image_url = _store_class_image(request.FILES.get('imagen'))
        except ValueError as error:
            return _json({'error': str(error)}, 400)
        with transaction.atomic():
            activity = _execute(
                'INSERT INTO actividad (nombre) VALUES (%s) ON CONFLICT (nombre) '
                'DO UPDATE SET activa = TRUE RETURNING actividad_id',
                (activity_name,),
            )
            created = _execute(
                "INSERT INTO sesion_clase (actividad_id, instructor_id, sala_id, inicio, fin, "
                "cupos_totales, nombre_sesion, precio, imagen_url, descripcion_sesion, intensidad, observaciones) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING sesion_id",
                (activity[0], instructor_id, room_id, start, end, capacity, name, price, image_url,
                 description or None, intensity, observations or None),
            )
        return _json({'sesion_id': created[0], 'message': 'Clase creada.'}, 201)
    except IntegrityError:
        if 'image_url' in locals() and image_url:
            _delete_class_image(image_url)
        return _json({'error': 'La sala o el instructor no están disponibles en ese horario, o los cupos superan la capacidad de la sala.'}, 409)
    except DatabaseError as error:
        if 'image_url' in locals() and image_url:
            _delete_class_image(image_url)
        if _postgres_error_code(error) == 'P0001':
            return _json({'error': 'La sala o el instructor no están disponibles, o los cupos superan la capacidad de la sala.'}, 409)
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['PATCH', 'POST'])
def update_session(request, session_id):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = request.POST if request.content_type.startswith('multipart/form-data') else _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud no es válido.'}, 400)
        activity_name = str(body.get('actividad', '')).strip()
        name = str(body.get('nombre', '')).strip() or activity_name
        start = parse_datetime(str(body.get('inicio', '')))
        end = parse_datetime(str(body.get('fin', '')))
        if start and timezone.is_naive(start):
            start = timezone.make_aware(start)
        if end and timezone.is_naive(end):
            end = timezone.make_aware(end)
        try:
            installation_id = int(body.get('instalacion_id'))
            instructor_id = int(body.get('instructor_id'))
            room_id = int(body.get('sala_id'))
            capacity = int(body.get('cupos_totales'))
            price = Decimal(str(body.get('precio', 0)))
        except (ValueError, TypeError, InvalidOperation):
            return _json({'error': 'Selecciona sede, instructor y sala; revisa también cupos y precio.'}, 400)
        if (not activity_name or not start or not end or end <= start or capacity < 1
                or installation_id < 1 or instructor_id < 1 or room_id < 1
                or not price.is_finite() or price < 0 or start <= timezone.now()):
            return _json({'error': 'Completa actividad, horario futuro, cupos y precio no negativo.'}, 400)
        if not _class_assignment_exists(installation_id, instructor_id, room_id):
            return _json({'error': 'El instructor y la sala deben pertenecer a la sede seleccionada.'}, 400)
        try:
            new_image_url = _store_class_image(request.FILES.get('imagen'))
        except ValueError as error:
            return _json({'error': str(error)}, 400)
        old_image_url = None
        with transaction.atomic():
            existing = _row(
                "SELECT sesion_id, imagen_url FROM sesion_clase WHERE sesion_id = %s "
                "AND estado = 'PROGRAMADA' AND inicio > CURRENT_TIMESTAMP FOR UPDATE",
                (session_id,),
            )
            if not existing:
                if new_image_url:
                    _delete_class_image(new_image_url)
                return _json({'error': 'La clase no existe, ya comenzó o no se puede modificar.'}, 409)
            old_image_url = existing['imagen_url']
            image_url = new_image_url or old_image_url
            activity = _execute(
                'INSERT INTO actividad (nombre) VALUES (%s) ON CONFLICT (nombre) '
                'DO UPDATE SET activa = TRUE RETURNING actividad_id',
                (activity_name,),
            )
            updated = _execute(
                "UPDATE sesion_clase SET actividad_id = %s, instructor_id = %s, sala_id = %s, "
                "inicio = %s, fin = %s, cupos_totales = %s, nombre_sesion = %s, precio = %s, imagen_url = %s "
                "WHERE sesion_id = %s AND estado = 'PROGRAMADA' AND inicio > CURRENT_TIMESTAMP "
                "RETURNING sesion_id",
                (activity[0], instructor_id, room_id, start, end, capacity, name, price, image_url, session_id),
            )
        if not updated:
            if new_image_url:
                _delete_class_image(new_image_url)
            return _json({'error': 'La clase no existe, ya comenzó o no se puede modificar.'}, 409)
        if new_image_url and old_image_url and old_image_url != new_image_url:
            _delete_class_image(old_image_url)
        return _json({'message': 'Clase actualizada.'})
    except IntegrityError:
        if 'new_image_url' in locals() and new_image_url:
            _delete_class_image(new_image_url)
        return _json({'error': 'La sala o el instructor no están disponibles en ese horario, o los cupos superan la capacidad de la sala.'}, 409)
    except DatabaseError as error:
        if 'new_image_url' in locals() and new_image_url:
            _delete_class_image(new_image_url)
        if _postgres_error_code(error) == 'P0001':
            return _json({'error': 'La sala o el instructor no están disponibles, o los cupos superan la capacidad de la sala.'}, 409)
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def reserve_session(request, session_id):
    try:
        persona, error = _require_persona(request, {'SOCIO'})
        if error:
            return error
        ids = _profile_ids(persona['rut'])
        if ids is None or ids['socio_id'] is None:
            return _json({'error': 'No se encontró el perfil de socio.'}, 409)
        with transaction.atomic():
            reservation = _execute(
                'SELECT * FROM reservar_clase(%s, %s)',
                (session_id, ids['socio_id']),
            )
            session = _row('SELECT precio FROM sesion_clase WHERE sesion_id = %s', (session_id,))
            payment_pending = False
            if session and session['precio'] > 0:
                body = _json_body(request) or {}
                method = str(body.get('metodo_pago', 'OTRO')).upper()
                if method not in {'EFECTIVO', 'DEBITO', 'CREDITO', 'TRANSFERENCIA', 'OTRO'}:
                    return _json({'error': 'Método de pago no válido.'}, 400)
                _execute(
                    "INSERT INTO pago_reserva (reserva_id, metodo, monto) "
                    "VALUES (%s, %s::metodo_pago, %s)",
                    (reservation[0], method, session['precio']),
                )
                payment_pending = True
        return _json({
            'reserva_id': reservation[0],
            'estado': reservation[1],
            'pago_pendiente': payment_pending,
            'message': 'Reserva confirmada.' if reservation[1] == 'RESERVADA' else 'Te agregamos a la lista de espera.',
        }, 201)
    except DatabaseError as error:
        if _postgres_error_code(error) == 'P0001':
            return _json({'error': 'No fue posible reservar. Revisa tu membresía, el horario y los cupos.'}, 409)
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def cancel_reservation(request, reservation_id):
    try:
        persona, error = _require_persona(request, {'SOCIO'})
        if error:
            return error
        ids = _profile_ids(persona['rut'])
        if ids is None or ids['socio_id'] is None:
            return _json({'error': 'No se encontró el perfil de socio.'}, 409)
        promoted = _execute('SELECT cancelar_reserva(%s, %s)', (reservation_id, ids['socio_id']))
        return _json({'message': 'Reserva cancelada.', 'personas_promovidas': promoted[0]})
    except DatabaseError as error:
        if _postgres_error_code(error) == 'P0001':
            return _json({'error': 'No fue posible cancelar. La reserva puede haber comenzado o no pertenecer a tu cuenta.'}, 409)
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def record_attendance(request, session_id):
    try:
        persona, error = _require_persona(request, {'INSTRUCTOR', 'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        reservation_id = int(body.get('reserva_id', 0))
        attended = body.get('asistio')
        if reservation_id < 1 or not isinstance(attended, bool):
            return _json({'error': 'Indica la reserva y si el socio asistió.'}, 400)
        if 'ADMINISTRADOR' not in persona['roles']:
            ids = _profile_ids(persona['rut'])
            instructor_id = ids['instructor_id'] if ids else None
            profile = _row(
                'SELECT tipo FROM perfil_instructor WHERE instructor_id = %s AND activo',
                (instructor_id,),
            ) if instructor_id else None
            if not profile or profile['tipo'] != 'MONITOR':
                return _json({'error': 'El registro de asistencia de clases corresponde a la especialidad Monitor.'}, 403)
            owns_session = _row(
                'SELECT 1 AS permitido FROM sesion_clase WHERE sesion_id = %s AND instructor_id = %s',
                (session_id, instructor_id),
            )
            if not owns_session:
                return _json({'error': 'Solo puedes registrar asistencia en tus clases.'}, 403)
        if not _row(
            'SELECT 1 AS permitido FROM reserva WHERE reserva_id = %s AND sesion_id = %s',
            (reservation_id, session_id),
        ):
            return _json({'error': 'La reserva no pertenece a la clase indicada.'}, 404)
        result = _execute(
            'SELECT registrar_asistencia_clase(%s, (SELECT socio_id FROM reserva WHERE reserva_id = %s), %s)',
            (reservation_id, reservation_id, attended),
        )
        return _json({'estado': result[0], 'message': 'Asistencia registrada.'})
    except ValueError:
        return _json({'error': 'Indica una reserva válida y si el socio asistió.'}, 400)
    except DatabaseError as error:
        if _postgres_error_code(error) == 'P0001':
            return _json({'error': 'No fue posible registrar asistencia. Verifica la reserva y el estado de la clase.'}, 409)
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def update_session_observations(request, session_id):
    try:
        persona, error = _require_persona(request, {'INSTRUCTOR'})
        if error:
            return error
        ids = _profile_ids(persona['rut'])
        instructor_id = ids['instructor_id'] if ids else None
        profile = _row(
            'SELECT tipo FROM perfil_instructor WHERE instructor_id = %s AND activo',
            (instructor_id,),
        ) if instructor_id else None
        if not profile or profile['tipo'] != 'MONITOR':
            return _json({'error': 'Las observaciones de clases corresponden a Monitor.'}, 403)
        body = _json_body(request)
        observations = body.get('observaciones') if body else None
        if not isinstance(observations, str) or len(observations.strip()) > 3000:
            return _json({'error': 'Ingresa observaciones válidas de hasta 3000 caracteres.'}, 400)
        if not _row(
            'SELECT 1 AS propia FROM sesion_clase WHERE sesion_id = %s AND instructor_id = %s',
            (session_id, instructor_id),
        ):
            return _json({'error': 'Solo puedes registrar observaciones en tus propias clases.'}, 403)
        updated = _execute(
            'UPDATE sesion_clase SET observaciones = %s '
            'WHERE sesion_id = %s AND instructor_id = %s RETURNING sesion_id',
            (observations.strip() or None, session_id, instructor_id),
        )
        if not updated:
            return _json({'error': 'No se encontró la clase para actualizar.'}, 404)
        return _json({'message': 'Observaciones de clase guardadas.'})
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['PATCH'])
def update_session_status(request, session_id):
    try:
        persona, error = _require_persona(request, {'INSTRUCTOR', 'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        status = body.get('estado') if body else None
        if status not in {'EN_CURSO', 'FINALIZADA', 'CANCELADA'}:
            return _json({'error': 'Estado no válido.'}, 400)
        if 'ADMINISTRADOR' not in persona['roles']:
            ids = _profile_ids(persona['rut'])
            instructor_id = ids['instructor_id'] if ids else None
            profile = _row(
                'SELECT tipo FROM perfil_instructor WHERE instructor_id = %s AND activo',
                (instructor_id,),
            ) if instructor_id else None
            if not profile or profile['tipo'] != 'MONITOR':
                return _json({'error': 'La gestión de clases corresponde a la especialidad Monitor.'}, 403)
            if not _row(
                'SELECT 1 AS permitido FROM sesion_clase WHERE sesion_id = %s AND instructor_id = %s',
                (session_id, instructor_id),
            ):
                return _json({'error': 'Solo puedes modificar tus propias clases.'}, 403)
        if status == 'CANCELADA':
            _execute('SELECT cancelar_sesion_clase(%s)', (session_id,))
        else:
            session = _row('SELECT inicio FROM sesion_clase WHERE sesion_id = %s', (session_id,))
            if status == 'EN_CURSO' and (not session or session['inicio'] > timezone.now()):
                return _json({'error': 'La clase aún no puede iniciarse.'}, 409)
            updated = _execute(
                "UPDATE sesion_clase SET estado = %s::estado_sesion "
                "WHERE sesion_id = %s AND estado IN ('PROGRAMADA', 'EN_CURSO') "
                'RETURNING sesion_id',
                (status, session_id),
            )
            if not updated:
                return _json({'error': 'La clase no existe o no admite ese cambio de estado.'}, 409)
        return _json({'message': 'Estado de clase actualizado.'})
    except DatabaseError as error:
        if _postgres_error_code(error) == 'P0001':
            return _json({'error': 'No fue posible cambiar el estado. Comprueba el horario de la clase.'}, 409)
        return _database_unavailable()
