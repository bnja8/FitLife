from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from django.db import DatabaseError, IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from ..google_maps import resolve_google_maps_url
from ..locations import valid_region_city
from .common import _database_unavailable, _execute, _json, _json_body, _profile_ids, _require_persona, _row, _rows


@csrf_exempt
@require_http_methods(['POST'])
def machines(request):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        name = str(body.get('nombre', '')).strip()
        category = str(body.get('categoria', '')).strip()
        observation = str(body.get('observacion', '')).strip() or None
        try:
            installation_id = int(body.get('instalacion_id'))
            room_id = int(body.get('sala_id'))
        except (ValueError, TypeError):
            return _json({'error': 'Selecciona una sede y una sala válidas para la máquina.'}, 400)
        if not name or len(name) > 120 or not category or len(category) > 80:
            return _json({'error': 'El nombre y la categoría son obligatorios y deben respetar el largo permitido.'}, 400)
        if installation_id < 1 or not _row(
            'SELECT instalacion_id FROM instalacion WHERE instalacion_id = %s AND activa',
            (installation_id,),
        ):
            return _json({'error': 'Selecciona una sede activa para la máquina.'}, 400)
        if room_id < 1 or not _row(
            'SELECT sa.sala_id FROM sala sa JOIN instalacion i USING (instalacion_id) '
            'WHERE sa.sala_id = %s AND sa.instalacion_id = %s AND sa.activa AND i.activa',
            (room_id, installation_id),
        ):
            return _json({'error': 'Selecciona una sala activa perteneciente a la sede elegida.'}, 400)
        result = _execute(
            'INSERT INTO maquina (nombre, categoria, instalacion_id, sala_id, observacion) '
            'VALUES (%s, %s, %s, %s, %s) '
            'RETURNING maquina_id',
            (name, category, installation_id, room_id, observation),
        )
        return _json({'maquina_id': result[0], 'message': 'Máquina agregada.'}, 201)
    except IntegrityError:
        return _json({'error': 'Ya existe una máquina con ese nombre.'}, 409)
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['GET', 'POST'])
def installations(request):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        if request.method == 'GET':
            return _json({'installations': _rows(
                'SELECT instalacion_id, nombre, direccion, aforo_maximo, '
                'region, ciudad, '
                'tiene_lockers, cantidad_lockers, tiene_estacionamiento, cupos_estacionamiento, '
                'tiene_vestidores, cantidad_vestidores, tiene_duchas, cantidad_duchas, '
                'horario_lunes_viernes, horario_sabados_dom_festivos, caracteristicas, latitud, longitud, '
                "CASE WHEN latitud IS NOT NULL AND longitud IS NOT NULL "
                "THEN CONCAT('https://maps.google.com/?q=', latitud, ',', longitud) END AS mapa_url, imagen_url, "
                'ARRAY(SELECT pm.plan_id FROM plan_membresia pm WHERE pm.activo AND NOT pm.acceso_todas_sedes '
                'AND EXISTS (SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id) ORDER BY pm.plan_id) AS plan_ids, '
                'ARRAY(SELECT ii.instructor_id FROM instalacion_instructor ii '
                'WHERE ii.instalacion_id = i.instalacion_id ORDER BY ii.instructor_id) AS instructor_ids, '
                'ARRAY(SELECT pm.nombre FROM plan_membresia pm WHERE pm.activo AND (pm.acceso_todas_sedes '
                'OR EXISTS (SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id)) ORDER BY pm.nombre) AS planes '
                'FROM instalacion i WHERE activa ORDER BY nombre'
            )})
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        try:
            values = _installation_values(body)
        except ValueError as error:
            return _json({'error': str(error)}, 400)
        installation_values, plan_ids = values[:-1], values[-1]
        with transaction.atomic():
            created = _execute(
                'INSERT INTO instalacion (nombre, direccion, region, ciudad, aforo_maximo, '
                'tiene_lockers, cantidad_lockers, '
                'tiene_estacionamiento, cupos_estacionamiento, tiene_vestidores, cantidad_vestidores, '
                'tiene_duchas, cantidad_duchas, horario_lunes_viernes, '
                'horario_sabados_dom_festivos, caracteristicas, latitud, longitud, imagen_url) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) '
                'RETURNING instalacion_id',
                installation_values,
            )
            _replace_installation_plans(created[0], plan_ids)
        return _json({'instalacion_id': created[0], 'message': 'Instalación agregada.'}, 201)
    except IntegrityError:
        return _json({'error': 'Ya existe una instalación con ese nombre.'}, 409)
    except DatabaseError:
        return _database_unavailable()


@require_http_methods(['GET'])
def public_installations(request):
    try:
        installations = _rows(
            'SELECT i.instalacion_id, i.nombre, i.direccion, i.region, i.ciudad, i.aforo_maximo, '
            'i.horario_lunes_viernes, i.horario_sabados_dom_festivos, i.caracteristicas, '
            'i.latitud, i.longitud, i.imagen_url, '
            'ARRAY(SELECT sa.nombre FROM sala sa WHERE sa.instalacion_id = i.instalacion_id '
            'AND sa.activa ORDER BY sa.nombre) AS areas '
            'FROM instalacion i WHERE i.activa AND i.direccion IS NOT NULL '
            'AND i.horario_lunes_viernes IS NOT NULL AND i.horario_sabados_dom_festivos IS NOT NULL '
            'AND i.latitud IS NOT NULL AND i.longitud IS NOT NULL ORDER BY i.nombre'
        )
        for installation in installations:
            installation['plans'] = _rows(
                'SELECT pm.plan_id, pm.tipo, pm.nombre, pm.descripcion, pm.duracion_dias, pm.precio_referencia, '
                'pm.acceso_todas_sedes, pm.es_prueba_gratuita '
                'FROM plan_membresia pm WHERE pm.activo AND (pm.acceso_todas_sedes OR EXISTS ('
                'SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = %s)) ORDER BY pm.precio_referencia, pm.nombre',
                (installation['instalacion_id'],),
            )
        sessions = _rows(
            "SELECT sc.sesion_id, COALESCE(sc.nombre_sesion, a.nombre) AS nombre, "
            "a.nombre AS actividad, sc.inicio, sc.fin, i.instalacion_id, sa.nombre AS sala, "
            "COALESCE(p.nombres || ' ' || p.\"apellidoPaterno\", 'Equipo FitLife') AS instructor "
            "FROM sesion_clase sc JOIN actividad a USING (actividad_id) "
            "JOIN sala sa USING (sala_id) JOIN instalacion i USING (instalacion_id) "
            "LEFT JOIN instructor ins ON ins.instructor_id = sc.instructor_id "
            "LEFT JOIN persona p ON p.rut = ins.rut "
            "WHERE sc.estado = 'PROGRAMADA' AND sc.inicio > CURRENT_TIMESTAMP "
            "AND sa.activa AND i.activa ORDER BY sc.inicio LIMIT 500"
        )
        return _json({'installations': installations, 'sessions': sessions})
    except DatabaseError:
        return _database_unavailable()


def _installation_values(body):
    name = str(body.get('nombre', '')).strip()
    address = str(body.get('direccion', '')).strip() or None
    region = body.get('region')
    city = body.get('ciudad')
    region = region.strip() if isinstance(region, str) else ''
    city = city.strip() if isinstance(city, str) else ''
    weekday_hours = str(body.get('horario_lunes_viernes', '')).strip() or None
    weekend_hours = str(body.get('horario_sabados_dom_festivos', '')).strip() or None
    characteristics = str(body.get('caracteristicas', '')).strip()
    try:
        capacity = int(body.get('aforo_maximo'))
        locker_count = int(body.get('cantidad_lockers', 0))
        parking_spaces = int(body.get('cupos_estacionamiento', 0))
        dressing_room_count = int(body.get('cantidad_vestidores', 0))
        shower_count = int(body.get('cantidad_duchas', 0))
    except (ValueError, TypeError):
        raise ValueError('Indica valores numéricos válidos para aforo y capacidad.') from None
    has_lockers = body.get('tiene_lockers', False)
    has_parking = body.get('tiene_estacionamiento', False)
    has_dressing_rooms = body.get('tiene_vestidores', False)
    has_showers = body.get('tiene_duchas', False)
    if not isinstance(has_lockers, bool):
        raise ValueError('Indica si la sede cuenta con lockers.')
    if not isinstance(has_parking, bool):
        raise ValueError('Indica si la sede cuenta con estacionamiento.')
    if not isinstance(has_dressing_rooms, bool):
        raise ValueError('Indica si la sede cuenta con vestidores.')
    if not isinstance(has_showers, bool):
        raise ValueError('Indica si la sede cuenta con duchas.')
    if not name or len(name) > 100 or capacity < 1:
        raise ValueError('El nombre de la sede y un aforo positivo son obligatorios.')
    if not address or len(address) > 200:
        raise ValueError('La dirección es obligatoria y no puede superar los 200 caracteres.')
    if not valid_region_city(region, city):
        raise ValueError('Selecciona una región y una ciudad o comuna válidas.')
    if not weekday_hours or not weekend_hours:
        raise ValueError('Debes ingresar los horarios de lunes a viernes y de sábados, domingos y feriados.')
    if any(len(hours) > 100 for hours in (weekday_hours or '', weekend_hours or '')):
        raise ValueError('El horario no puede superar los 100 caracteres.')
    if len(characteristics) > 3000:
        raise ValueError('Las características superan el largo permitido.')
    if locker_count < 0 or (has_lockers and locker_count < 1) or (not has_lockers and locker_count != 0):
        raise ValueError('La cantidad debe ser positiva si hay lockers y cero si no hay.')
    if parking_spaces < 0 or (has_parking and parking_spaces < 1) or (not has_parking and parking_spaces != 0):
        raise ValueError('Los cupos deben ser positivos si hay estacionamiento y cero si no hay.')
    if dressing_room_count < 0 or (has_dressing_rooms and dressing_room_count < 1) \
            or (not has_dressing_rooms and dressing_room_count != 0):
        raise ValueError('La cantidad debe ser positiva si hay vestidores y cero si no hay.')
    if shower_count < 0 or (has_showers and shower_count < 1) \
            or (not has_showers and shower_count != 0):
        raise ValueError('La cantidad debe ser positiva si hay duchas y cero si no hay.')
    try:
        if body.get('mapa_url'):
            latitude, longitude = resolve_google_maps_url(body['mapa_url'])
        else:
            latitude = Decimal(str(body.get('latitud'))) if body.get('latitud') not in (None, '') else None
            longitude = Decimal(str(body.get('longitud'))) if body.get('longitud') not in (None, '') else None
    except InvalidOperation as error:
        raise ValueError('Indica coordenadas válidas para el mapa.') from error
    except ValueError:
        raise
    if latitude is None or longitude is None:
        if 'latitud' in body or 'longitud' in body:
            raise ValueError('La latitud y la longitud deben proporcionarse juntas.')
        raise ValueError('Pega el enlace de Google Maps de la sede para ubicarla.')
    if latitude is not None and (
        not latitude.is_finite() or not longitude.is_finite()
        or not Decimal('-90') <= latitude <= Decimal('90')
        or not Decimal('-180') <= longitude <= Decimal('180')
    ):
        raise ValueError('Las coordenadas están fuera del rango válido.')
    image_url = str(body.get('imagen_url', '')).strip() or None
    if image_url:
        parsed_image_url = urlsplit(image_url)
        if len(image_url) > 500 or (
            parsed_image_url.scheme not in {'http', 'https'}
            and not image_url.startswith(('/media/', '/static/'))
        ) or (parsed_image_url.scheme in {'http', 'https'} and not parsed_image_url.netloc):
            raise ValueError('La imagen debe ser una URL HTTP/HTTPS o una ruta local /media/ o /static/.')
    raw_plan_ids = body.get('planes_ids', [])
    if not isinstance(raw_plan_ids, list):
        raise ValueError('Selecciona una lista válida de suscripciones para la sede.')
    if any(
        isinstance(plan_id, bool)
        or not isinstance(plan_id, int) and not str(plan_id).isdigit()
        for plan_id in raw_plan_ids
    ):
        raise ValueError('Selecciona suscripciones válidas para la sede.')
    try:
        plan_ids = sorted({int(plan_id) for plan_id in raw_plan_ids})
    except (ValueError, TypeError):
        raise ValueError('Selecciona suscripciones válidas para la sede.') from None
    if any(plan_id < 1 for plan_id in plan_ids):
        raise ValueError('Selecciona suscripciones válidas para la sede.')
    if plan_ids:
        available_plan_ids = {
            row['plan_id'] for row in _rows(
                'SELECT plan_id FROM plan_membresia WHERE activo AND NOT acceso_todas_sedes AND plan_id = ANY(%s)',
                (plan_ids,),
            )
        }
        if available_plan_ids != set(plan_ids):
            raise ValueError('Una o más suscripciones ya no están disponibles.')
    return (
        name, address, region, city, capacity, has_lockers, locker_count, has_parking, parking_spaces,
        has_dressing_rooms, dressing_room_count, has_showers, shower_count,
        weekday_hours, weekend_hours, characteristics, latitude, longitude, image_url, plan_ids,
    )


def _replace_installation_plans(installation_id, plan_ids):
    _execute('DELETE FROM instalacion_plan WHERE instalacion_id = %s', (installation_id,))
    for plan_id in plan_ids:
        _execute(
            'INSERT INTO instalacion_plan (instalacion_id, plan_id) VALUES (%s, %s)',
            (installation_id, plan_id),
        )


@csrf_exempt
@require_http_methods(['PATCH'])
def installation_detail(request, installation_id):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        try:
            values = _installation_values(body)
        except ValueError as error:
            return _json({'error': str(error)}, 400)
        installation_values, plan_ids = values[:-1], values[-1]
        with transaction.atomic():
            updated = _execute(
                'UPDATE instalacion SET nombre = %s, direccion = %s, region = %s, ciudad = %s, aforo_maximo = %s, '
                'tiene_lockers = %s, cantidad_lockers = %s, tiene_estacionamiento = %s, '
                'cupos_estacionamiento = %s, tiene_vestidores = %s, cantidad_vestidores = %s, '
                'tiene_duchas = %s, cantidad_duchas = %s, horario_lunes_viernes = %s, '
                'horario_sabados_dom_festivos = %s, caracteristicas = %s, latitud = %s, longitud = %s, '
                'imagen_url = %s '
                'WHERE instalacion_id = %s AND activa RETURNING instalacion_id',
                (*installation_values, installation_id),
            )
            if updated is not None:
                _replace_installation_plans(installation_id, plan_ids)
        if updated is None:
            return _json({'error': 'Sede no encontrada.'}, 404)
        return _json({'message': 'Sede actualizada.'})
    except IntegrityError:
        return _json({'error': 'Ya existe una sede con ese nombre.'}, 409)
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['PUT'])
def installation_instructors(request, installation_id):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        instructor_ids = body.get('instructor_ids') if body else None
        if not isinstance(instructor_ids, list) or any(
            isinstance(value, bool) or not str(value).isdigit() or int(value) < 1
            for value in instructor_ids
        ):
            return _json({'error': 'Selecciona una lista válida de instructores.'}, 400)
        selected_ids = sorted({int(value) for value in instructor_ids})
        if not _row(
            'SELECT instalacion_id FROM instalacion WHERE instalacion_id = %s AND activa',
            (installation_id,),
        ):
            return _json({'error': 'Sede no encontrada.'}, 404)
        if selected_ids:
            active_ids = {
                row['instructor_id'] for row in _rows(
                    'SELECT i.instructor_id FROM instructor i '
                    'JOIN perfil_instructor pi USING (instructor_id) '
                    'WHERE i.activo AND pi.activo AND i.instructor_id = ANY(%s)',
                    (selected_ids,),
                )
            }
            if active_ids != set(selected_ids):
                return _json({'error': 'Uno o más profesionales no están activos o no tienen perfil.'}, 400)
        with transaction.atomic():
            existing_ids = {
                row['instructor_id'] for row in _rows(
                    'SELECT instructor_id FROM instalacion_instructor '
                    'WHERE instalacion_id = %s FOR UPDATE',
                    (installation_id,),
                )
            }
            removed_ids = existing_ids - set(selected_ids)
            if removed_ids and _rows(
                "SELECT sc.sesion_id FROM sesion_clase sc "
                "JOIN sala sa USING (sala_id) "
                "WHERE sa.instalacion_id = %s AND sc.instructor_id = ANY(%s) "
                "AND sc.estado IN ('PROGRAMADA', 'EN_CURSO') "
                "AND (sc.estado = 'EN_CURSO' OR sc.inicio > CURRENT_TIMESTAMP) "
                "LIMIT 1",
                (installation_id, list(removed_ids)),
            ):
                return _json({
                    'error': 'No puedes retirar profesionales asignados a clases activas o futuras.'
                }, 409)
            for instructor_id in removed_ids:
                _execute(
                    'DELETE FROM instalacion_instructor '
                    'WHERE instalacion_id = %s AND instructor_id = %s',
                    (installation_id, instructor_id),
                )
            for instructor_id in set(selected_ids) - existing_ids:
                _execute(
                    'INSERT INTO instalacion_instructor (instalacion_id, instructor_id) '
                    'VALUES (%s, %s)',
                    (installation_id, instructor_id),
                )
        return _json({'message': 'Profesionales asignados a la sede.'})
    except IntegrityError:
        return _json({'error': 'No se pudieron actualizar los profesionales de la sede.'}, 409)
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def rooms(request):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        if request.method == 'GET':
            return _json({'rooms': _rows(
                'SELECT sa.sala_id, sa.nombre, sa.capacidad, sa.instalacion_id, '
                'i.nombre AS instalacion FROM sala sa '
                'JOIN instalacion i USING (instalacion_id) '
                'WHERE sa.activa ORDER BY i.nombre, sa.nombre'
            )})
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        name = str(body.get('nombre', '')).strip()
        try:
            installation_id = int(body.get('instalacion_id'))
            capacity = int(body.get('capacidad'))
        except (ValueError, TypeError):
            return _json({'error': 'Selecciona una instalación e indica una capacidad válida.'}, 400)
        if not name or len(name) > 100 or capacity < 1:
            return _json({'error': 'El nombre de la sala y una capacidad positiva son obligatorios.'}, 400)
        if not _row(
            'SELECT instalacion_id FROM instalacion WHERE instalacion_id = %s AND activa',
            (installation_id,),
        ):
            return _json({'error': 'Selecciona una sede activa.'}, 400)
        created = _execute(
            'INSERT INTO sala (instalacion_id, nombre, capacidad) VALUES (%s, %s, %s) '
            'RETURNING sala_id',
            (installation_id, name, capacity),
        )
        return _json({'sala_id': created[0], 'message': 'Sala agregada.'}, 201)
    except IntegrityError:
        return _json({'error': 'Ya existe una sala con ese nombre en la instalación seleccionada.'}, 409)
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['POST'])
def access_points(request):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        name = str(body.get('nombre', '')).strip()
        access_type = str(body.get('tipo', 'BIDIRECCIONAL')).upper()
        usage = str(body.get('uso', 'GENERAL')).upper()
        installation_value = body.get('instalacion_id')
        if (
            isinstance(installation_value, bool)
            or not isinstance(installation_value, (int, str))
            or isinstance(installation_value, str) and not installation_value.isdecimal()
        ):
            return _json({'error': 'Selecciona una sede válida.'}, 400)
        try:
            installation_id = int(installation_value)
        except (ValueError, TypeError):
            return _json({'error': 'Selecciona una sede válida.'}, 400)
        if not name or len(name) > 100:
            return _json({'error': 'El nombre del punto de acceso es obligatorio (máximo 100 caracteres).'}, 400)
        if access_type not in {'ENTRADA', 'SALIDA', 'BIDIRECCIONAL'}:
            return _json({'error': 'Selecciona un tipo válido para el punto de acceso.'}, 400)
        if usage not in {'GENERAL', 'ESTACIONAMIENTO'}:
            return _json({'error': 'Selecciona un uso válido para el punto de acceso.'}, 400)
        installation = _row(
            'SELECT instalacion_id, tiene_estacionamiento FROM instalacion '
            'WHERE instalacion_id = %s AND activa',
            (installation_id,),
        )
        if installation is None:
            return _json({'error': 'Selecciona una sede activa.'}, 400)
        if usage == 'ESTACIONAMIENTO' and not installation['tiene_estacionamiento']:
            return _json({'error': 'Solo puedes crear un punto de estacionamiento en una sede que cuente con estacionamiento.'}, 400)
        created = _execute(
            'INSERT INTO punto_acceso (instalacion_id, nombre, tipo, uso) '
            'VALUES (%s, %s, %s::tipo_punto_acceso, %s) RETURNING punto_acceso_id',
            (installation_id, name, access_type, usage),
        )
        return _json({'punto_acceso_id': created[0], 'message': 'Punto de acceso agregado.'}, 201)
    except IntegrityError:
        return _json({'error': 'Ya existe un punto con ese nombre en la sede seleccionada.'}, 409)
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['PATCH'])
def access_point_detail(request, access_point_id):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        active = body.get('activo') if body else None
        if not isinstance(active, bool):
            return _json({'error': 'Indica si el punto de acceso debe quedar activo.'}, 400)
        updated = _execute(
            'UPDATE punto_acceso SET activo = %s WHERE punto_acceso_id = %s '
            'RETURNING punto_acceso_id',
            (active, access_point_id),
        )
        if updated is None:
            return _json({'error': 'Punto de acceso no encontrado.'}, 404)
        return _json({'message': 'Estado del punto de acceso actualizado.'})
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['PATCH'])
def machine_detail(request, machine_id):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if not body:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        updates = []
        params = []
        state = body.get('estado')
        if state is not None:
            if state not in {'OPERATIVA', 'MANTENCION', 'FUERA_SERVICIO'}:
                return _json({'error': 'Estado de máquina no válido.'}, 400)
            updates.append('estado = %s')
            params.append(state)
        if 'instalacion_id' in body:
            try:
                installation_id = int(body['instalacion_id'])
            except (ValueError, TypeError):
                return _json({'error': 'Selecciona una sede válida para la máquina.'}, 400)
            if installation_id < 1 or not _row(
                'SELECT instalacion_id FROM instalacion WHERE instalacion_id = %s AND activa',
                (installation_id,),
            ):
                return _json({'error': 'Selecciona una sede activa para la máquina.'}, 400)
            updates.append('instalacion_id = %s')
            params.append(installation_id)
        if 'sala_id' in body:
            try:
                room_id = int(body['sala_id'])
            except (ValueError, TypeError):
                return _json({'error': 'Selecciona una sala válida para la máquina.'}, 400)
            if room_id < 1:
                return _json({'error': 'Selecciona una sala válida para la máquina.'}, 400)
            machine = _row(
                'SELECT instalacion_id FROM maquina WHERE maquina_id = %s',
                (machine_id,),
            )
            if machine is None:
                return _json({'error': 'Máquina no encontrada.'}, 404)
            try:
                target_installation_id = int(body.get('instalacion_id', machine['instalacion_id']))
            except (TypeError, ValueError):
                return _json({'error': 'Asigna la máquina a una sede antes de elegir una sala.'}, 400)
            if not _row(
                'SELECT sa.sala_id FROM sala sa JOIN instalacion i USING (instalacion_id) '
                'WHERE sa.sala_id = %s AND sa.instalacion_id = %s AND sa.activa AND i.activa',
                (room_id, target_installation_id),
            ):
                return _json({'error': 'Selecciona una sala activa perteneciente a la sede elegida.'}, 400)
            updates.append('sala_id = %s')
            params.append(room_id)
        elif 'instalacion_id' in body:
            machine = _row(
                'SELECT maquina.sala_id FROM maquina WHERE maquina_id = %s',
                (machine_id,),
            )
            if machine is not None and machine['sala_id'] is not None and not _row(
                'SELECT sala_id FROM sala WHERE sala_id = %s AND instalacion_id = %s',
                (machine['sala_id'], installation_id),
            ):
                return _json({'error': 'Asigna una sala de la nueva sede antes de trasladar la máquina.'}, 400)
        if not updates:
            return _json({'error': 'Indica el estado o la sede a actualizar.'}, 400)
        params.append(machine_id)
        result = _execute(
            f'UPDATE maquina SET {", ".join(updates)}, actualizada_en = CURRENT_TIMESTAMP '
            'WHERE maquina_id = %s RETURNING maquina_id',
            params,
        )
        if result is None:
            return _json({'error': 'Máquina no encontrada.'}, 404)
        return _json({'message': 'Estado de máquina actualizado.'})
    except DatabaseError:
        return _database_unavailable()

@csrf_exempt
@require_http_methods(['GET', 'POST'])
def followups(request):
    try:
        persona, error = _require_persona(request, {'INSTRUCTOR'})
        if error:
            return error
        ids = _profile_ids(persona['rut'])
        instructor_id = ids['instructor_id'] if ids else None
        if not instructor_id:
            return _json({'error': 'No se encontró tu perfil profesional.'}, 409)
        profile = _row(
            'SELECT tipo FROM perfil_instructor WHERE instructor_id = %s AND activo',
            (instructor_id,),
        )
        if not profile:
            return _json({'error': 'No se encontró tu especialidad profesional activa.'}, 409)
        if profile['tipo'] == 'MONITOR':
            return _json({'error': 'Los registros de entrenamiento no están habilitados para Monitor.'}, 403)
        return _json({
            'error': 'Los seguimientos genéricos fueron reemplazados por herramientas específicas de cada especialidad.',
        }, 410)
    except DatabaseError:
        return _database_unavailable()
