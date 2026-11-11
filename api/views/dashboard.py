from django.db import DatabaseError
from django.views.decorators.http import require_http_methods

from ..locations import REGION_CITIES
from .common import _database_unavailable, _json, _profile_ids, _require_persona, _row, _rows


@require_http_methods(['GET'])
def dashboard(request):
    try:
        persona, error = _require_persona(request)
        if error:
            return error
        roles = persona['roles']
        ids = _profile_ids(persona['rut'])
        professional = _row(
            'SELECT pi.tipo, pi.especialidad FROM instructor i '
            'LEFT JOIN perfil_instructor pi USING (instructor_id) WHERE i.rut = %s',
            (persona['rut'],),
        )
        data = {
            'user': persona,
            'roles': roles,
            'professional_profile': professional,
            'sessions': _rows(
                "SELECT sc.sesion_id, COALESCE(sc.nombre_sesion, a.nombre) AS nombre, "
                "a.nombre AS actividad, a.descripcion, sc.imagen_url, v.instructor, v.sala, sc.inicio, sc.fin, "
                "sc.actividad_id, sc.instructor_id, sc.sala_id, "
                "(SELECT instalacion_id FROM sala WHERE sala_id = sc.sala_id) AS instalacion_id, "
                "sc.estado, sc.cupos_totales, v.cupos_ocupados, v.cupos_disponibles, "
                "v.personas_en_espera, sc.precio "
                "FROM sesion_clase sc JOIN actividad a USING (actividad_id) "
                "JOIN sala sa USING (sala_id) "
                "JOIN vw_disponibilidad_clases v USING (sesion_id) "
                "WHERE sc.estado = 'PROGRAMADA' AND sc.inicio > CURRENT_TIMESTAMP "
                "ORDER BY sc.inicio LIMIT 100"
            ),
            'activities': _rows('SELECT actividad_id, nombre FROM actividad WHERE activa ORDER BY nombre'),
            'gym_locations': _rows(
                'SELECT instalacion_id, nombre, direccion, aforo_maximo, tiene_lockers, '
                'region, ciudad, '
                'cantidad_lockers, tiene_estacionamiento, cupos_estacionamiento, '
                'horario_lunes_viernes, horario_sabados_dom_festivos, caracteristicas, latitud, longitud, '
                "CASE WHEN latitud IS NOT NULL AND longitud IS NOT NULL "
                "THEN CONCAT('https://maps.google.com/?q=', latitud, ',', longitud) END AS mapa_url, imagen_url, "
                'ARRAY(SELECT sa.nombre FROM sala sa WHERE sa.instalacion_id = i.instalacion_id '
                'AND sa.activa ORDER BY sa.nombre) AS areas, '
                'ARRAY(SELECT pm.plan_id FROM plan_membresia pm WHERE pm.activo AND NOT pm.acceso_todas_sedes '
                'AND EXISTS (SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id) ORDER BY pm.plan_id) AS plan_ids, '
                'ARRAY(SELECT pm.nombre FROM plan_membresia pm WHERE pm.activo AND (pm.acceso_todas_sedes '
                'OR EXISTS (SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id)) ORDER BY pm.nombre) AS planes '
                'FROM instalacion i WHERE i.activa ORDER BY i.nombre'
            ),
            'plans': _rows(
                'SELECT plan_id, tipo, nombre, descripcion, duracion_dias, precio_referencia, '
                'incluye_entrenador_personal, incluye_lockers, incluye_estacionamiento, otros_beneficios, '
                'acceso_todas_sedes, es_prueba_gratuita '
                'FROM plan_membresia WHERE activo ORDER BY precio_referencia'
            ),
            'gym_sessions': _rows(
                "SELECT sc.sesion_id, COALESCE(sc.nombre_sesion, a.nombre) AS nombre, "
                "a.nombre AS actividad, sc.inicio, sc.fin, i.instalacion_id, sa.nombre AS sala, "
                "COALESCE(p.nombres || ' ' || p.\"apellidoPaterno\", 'Equipo FitLife') AS instructor "
                "FROM sesion_clase sc JOIN actividad a USING (actividad_id) "
                "JOIN sala sa USING (sala_id) JOIN instalacion i USING (instalacion_id) "
                "LEFT JOIN instructor ins ON ins.instructor_id = sc.instructor_id "
                "LEFT JOIN persona p ON p.rut = ins.rut "
                "WHERE sc.estado = 'PROGRAMADA' AND sc.inicio > CURRENT_TIMESTAMP "
                "AND sa.activa AND i.activa ORDER BY sc.inicio LIMIT 500"
            ),
        }
        if ids and ids['socio_id'] is not None:
            data['memberships'] = _rows(
                'SELECT membresia_id, plan, estado_calculado AS estado, fecha_inicio, fecha_fin, '
                'precio_acordado, incluye_entrenador_personal, incluye_lockers, '
                'incluye_estacionamiento, otros_beneficios, instalacion_id, sede, '
                'acceso_todas_sedes, es_prueba_gratuita '
                'FROM vw_membresias WHERE socio_id = %s '
                'ORDER BY fecha_fin DESC NULLS LAST, membresia_id DESC',
                (ids['socio_id'],),
            )
            data['reservations'] = _rows(
                'SELECT r.reserva_id, r.estado, r.creada_en, sc.sesion_id, '
                'COALESCE(sc.nombre_sesion, a.nombre) AS nombre, a.nombre AS actividad, '
                'sc.inicio, sc.fin, sa.nombre AS sala FROM reserva r '
                'JOIN sesion_clase sc USING (sesion_id) JOIN actividad a USING (actividad_id) '
                'JOIN sala sa USING (sala_id) WHERE r.socio_id = %s AND r.estado <> %s '
                'ORDER BY sc.inicio DESC LIMIT 50',
                (ids['socio_id'], 'CANCELADA'),
            )
            data['training'] = _rows(
                'SELECT st.tipo, st.titulo, st.detalle, st.progreso, st.fecha_objetivo, '
                'p.nombres || %s || p."apellidoPaterno" AS profesional FROM seguimiento_entrenamiento st '
                'JOIN instructor i USING (instructor_id) JOIN persona p ON p.rut = i.rut '
                "WHERE st.socio_id = %s AND st.tipo IN ('PLAN', 'OBJETIVO') "
                'ORDER BY st.creada_en DESC LIMIT 10',
                (' ', ids['socio_id']),
            )
        if 'ADMINISTRADOR' in roles or 'RECEPCIONISTA' in roles:
            reception_only = 'RECEPCIONISTA' in roles and 'ADMINISTRADOR' not in roles
            installation_id = persona.get('recepcionista_instalacion_id')
            if reception_only and installation_id is None:
                data['occupancy'] = []
                data['recent_access'] = []
                data['access_points'] = []
                data['summary'] = {
                    'socios': 0, 'presentes': 0, 'membresias_vencidas': 0, 'clases_hoy': 0,
                }
            else:
                data['occupancy'] = _rows(
                    'SELECT * FROM vw_aforo_actual WHERE instalacion_id = %s ORDER BY instalacion'
                    if reception_only else 'SELECT * FROM vw_aforo_actual ORDER BY instalacion',
                    (installation_id,) if reception_only else (),
                )
                data['recent_access'] = _rows(
                    'SELECT v.* FROM vw_accesos_recientes v '
                    'JOIN evento_acceso ea USING (evento_id) '
                    'JOIN punto_acceso pa USING (punto_acceso_id) '
                    'WHERE pa.instalacion_id = %s ORDER BY v.registrado_en DESC LIMIT 8'
                    if reception_only else
                    'SELECT * FROM vw_accesos_recientes ORDER BY registrado_en DESC LIMIT 8',
                    (installation_id,) if reception_only else (),
                )
                data['access_points'] = _rows(
                    'SELECT pa.punto_acceso_id, pa.nombre, pa.uso, i.nombre AS instalacion '
                    'FROM punto_acceso pa JOIN instalacion i USING (instalacion_id) '
                    "WHERE pa.activo AND i.activa "
                    "AND (pa.uso <> 'ESTACIONAMIENTO' OR i.tiene_estacionamiento) "
                    + ('AND i.instalacion_id = %s ' if reception_only else '')
                    + 'ORDER BY i.nombre, pa.nombre',
                    (installation_id,) if reception_only else (),
                )
                data['summary'] = _row(
                    'SELECT (SELECT COUNT(DISTINCT socio_id) FROM vw_membresias '
                    "WHERE estado_calculado = 'ACTIVA' AND (instalacion_id = %s OR acceso_todas_sedes)) AS socios, "
                    '(SELECT COALESCE(personas_presentes, 0) FROM vw_aforo_actual '
                    'WHERE instalacion_id = %s) AS presentes, '
                    "(SELECT COUNT(*) FROM vw_membresias WHERE estado_calculado = 'VENCIDA' "
                    'AND (instalacion_id = %s OR acceso_todas_sedes)) AS membresias_vencidas, '
                    "(SELECT COUNT(*) FROM sesion_clase sc JOIN sala sa USING (sala_id) "
                    "WHERE sc.inicio::date = CURRENT_DATE AND sc.estado IN ('PROGRAMADA', 'EN_CURSO') "
                    'AND sa.instalacion_id = %s) AS clases_hoy'
                    if reception_only else
                    'SELECT (SELECT COUNT(*) FROM socio WHERE activo) AS socios, '
                    '(SELECT COUNT(*) FROM presencia_actual) AS presentes, '
                    "(SELECT COUNT(*) FROM membresia WHERE estado = 'VENCIDA') AS membresias_vencidas, "
                    "(SELECT COUNT(*) FROM sesion_clase WHERE inicio::date = CURRENT_DATE "
                    "AND estado IN ('PROGRAMADA', 'EN_CURSO')) AS clases_hoy",
                    (installation_id, installation_id, installation_id, installation_id) if reception_only else (),
                )
        if 'ADMINISTRADOR' in roles:
            data['location_options'] = REGION_CITIES
            data['admin_access_points'] = _rows(
                'SELECT pa.punto_acceso_id, pa.instalacion_id, i.nombre AS instalacion, '
                'pa.nombre, pa.tipo, pa.uso, pa.activo, i.tiene_estacionamiento '
                'FROM punto_acceso pa '
                'JOIN instalacion i USING (instalacion_id) '
                'ORDER BY i.nombre, pa.nombre'
            )
            data['admin_sessions'] = _rows(
                "SELECT sc.sesion_id, COALESCE(sc.nombre_sesion, a.nombre) AS nombre, "
                "a.nombre AS actividad, a.descripcion, sc.imagen_url, v.instructor, v.sala, "
                "sc.inicio, sc.fin, sc.actividad_id, sc.instructor_id, sc.sala_id, sa.instalacion_id, "
                "sc.estado, sc.cupos_totales, v.cupos_ocupados, v.cupos_disponibles, "
                "v.personas_en_espera, sc.precio "
                "FROM sesion_clase sc JOIN actividad a USING (actividad_id) "
                "JOIN sala sa USING (sala_id) "
                "JOIN vw_disponibilidad_clases v USING (sesion_id) "
                "ORDER BY sc.inicio DESC LIMIT 100"
            )
            data['users'] = _rows(
                'SELECT p.rut, p.nombres, p."apellidoPaterno" AS apellido_paterno, '
                'p.correo, u.activo, s.socio_id, pi.tipo AS tipo_profesional, pi.especialidad, '
                'rs.instalacion_id AS recepcionista_instalacion_id, ri.nombre AS recepcionista_instalacion, '
                'ARRAY(SELECT r.codigo FROM usuario_rol ur '
                'JOIN rol r USING (rol_id) WHERE ur.rut = p.rut ORDER BY r.codigo) AS roles '
                'FROM persona p JOIN usuario u ON u.rut = p.rut '
                'LEFT JOIN socio s ON s.rut = p.rut '
                'LEFT JOIN instructor ins ON ins.rut = p.rut '
                'LEFT JOIN perfil_instructor pi USING (instructor_id) '
                'LEFT JOIN recepcionista_sede rs ON rs.rut = p.rut '
                'LEFT JOIN instalacion ri ON ri.instalacion_id = rs.instalacion_id '
                'ORDER BY p.nombres LIMIT 100'
            )
            data['admin_memberships'] = _rows(
                'SELECT membresia_id, socio, plan, estado_calculado AS estado, '
                'fecha_inicio, fecha_fin, precio_acordado, incluye_entrenador_personal, '
                'incluye_lockers, incluye_estacionamiento, otros_beneficios, instalacion_id, sede, '
                'acceso_todas_sedes, es_prueba_gratuita '
                'FROM vw_membresias ORDER BY fecha_inicio DESC NULLS LAST, membresia_id DESC LIMIT 500'
            )
            data['machines'] = _rows(
                'SELECT m.maquina_id, m.nombre, m.categoria, m.instalacion_id, m.sala_id, '
                'sa.nombre AS sala, m.estado, m.observacion '
                'FROM maquina m LEFT JOIN sala sa USING (sala_id) ORDER BY m.nombre'
            )
            data['rooms'] = _rows(
                'SELECT sa.sala_id, sa.nombre, sa.capacidad, sa.instalacion_id, i.nombre AS instalacion '
                'FROM sala sa JOIN instalacion i USING (instalacion_id) '
                'WHERE sa.activa ORDER BY i.nombre, sa.nombre'
            )
            data['installations'] = _rows(
                'SELECT i.instalacion_id, i.nombre, i.direccion, i.region, i.ciudad, i.aforo_maximo, '
                'i.tiene_lockers, i.cantidad_lockers, i.tiene_estacionamiento, i.cupos_estacionamiento, '
                'i.tiene_vestidores, i.cantidad_vestidores, i.tiene_duchas, i.cantidad_duchas, '
                'i.horario_lunes_viernes, i.horario_sabados_dom_festivos, i.caracteristicas, '
                'i.latitud, i.longitud, i.imagen_url, '
                'ARRAY(SELECT ii.instructor_id FROM instalacion_instructor ii '
                'WHERE ii.instalacion_id = i.instalacion_id ORDER BY ii.instructor_id) AS instructor_ids, '
                'ARRAY(SELECT pm.plan_id FROM plan_membresia pm WHERE pm.activo AND NOT pm.acceso_todas_sedes '
                'AND EXISTS (SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id) ORDER BY pm.plan_id) AS plan_ids, '
                'ARRAY(SELECT pm.nombre FROM plan_membresia pm WHERE pm.activo AND (pm.acceso_todas_sedes '
                'OR EXISTS (SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id)) ORDER BY pm.nombre) AS planes '
                'FROM instalacion i WHERE i.activa ORDER BY i.nombre'
            )
            data['instructors'] = _rows(
                'SELECT i.instructor_id, p.nombres || %s || p."apellidoPaterno" AS nombre, '
                'COALESCE(pi.tipo, %s) AS tipo, pi.especialidad, '
                'ARRAY(SELECT ii.instalacion_id FROM instalacion_instructor ii '
                'WHERE ii.instructor_id = i.instructor_id ORDER BY ii.instalacion_id) AS instalacion_ids '
                'FROM instructor i JOIN persona p ON p.rut = i.rut '
                'LEFT JOIN perfil_instructor pi USING (instructor_id) '
                'WHERE i.activo ORDER BY nombre',
                (' ', 'MONITOR'),
            )
            data['waitlist'] = _rows(
                'SELECT * FROM vw_lista_espera ORDER BY creada_en LIMIT 20'
            )
        if 'INSTRUCTOR' in roles:
            instructor = ids['instructor_id'] if ids else None
            if professional and professional['tipo'] == 'MONITOR':
                data['instructor_id'] = instructor
                data['instructor_sessions'] = _rows(
                    "SELECT sc.sesion_id, COALESCE(sc.nombre_sesion, a.nombre) AS nombre, "
                    "a.nombre AS actividad, a.descripcion, sc.descripcion_sesion, sc.intensidad, sc.observaciones, "
                    "sc.inicio, sc.fin, sc.estado, sc.sala_id, sa.nombre AS sala, "
                    "sa.instalacion_id, sc.cupos_totales, v.cupos_ocupados, v.cupos_disponibles, "
                    "v.personas_en_espera, sc.precio, sc.imagen_url "
                    "FROM sesion_clase sc JOIN actividad a USING (actividad_id) "
                    "JOIN sala sa USING (sala_id) JOIN vw_disponibilidad_clases v USING (sesion_id) "
                    "WHERE sc.instructor_id = %s ORDER BY sc.inicio DESC LIMIT 100",
                    (instructor,),
                ) if instructor else []
                if 'ADMINISTRADOR' not in roles:
                    data['installations'] = _rows(
                        'SELECT i.instalacion_id, i.nombre FROM instalacion i '
                        'JOIN instalacion_instructor ii USING (instalacion_id) '
                        'WHERE ii.instructor_id = %s AND i.activa ORDER BY i.nombre',
                        (instructor,),
                    ) if instructor else []
                    data['rooms'] = _rows(
                        'SELECT sa.sala_id, sa.nombre, sa.capacidad, sa.instalacion_id '
                        'FROM sala sa JOIN instalacion_instructor ii USING (instalacion_id) '
                        'WHERE ii.instructor_id = %s AND sa.activa ORDER BY sa.nombre',
                        (instructor,),
                    ) if instructor else []
                data['attendees'] = _rows(
                    "SELECT r.reserva_id, r.sesion_id, r.estado, sc.estado AS estado_sesion, "
                    "sc.inicio, COALESCE(sc.nombre_sesion, a.nombre) AS clase, "
                    "s.socio_id, p.nombres || %s || p.\"apellidoPaterno\" AS socio "
                    'FROM reserva r JOIN sesion_clase sc USING (sesion_id) '
                    'JOIN actividad a USING (actividad_id) JOIN socio s USING (socio_id) '
                    'JOIN persona p ON p.rut = s.rut WHERE sc.instructor_id = %s '
                    "AND r.estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE') "
                    'ORDER BY sc.inicio, r.creada_en LIMIT 100',
                    (' ', instructor),
                ) if instructor else []
                data['followups'] = []
            else:
                data['instructor_sessions'] = []
                data['attendees'] = []
                data['followups'] = []
        return _json(data)
    except DatabaseError:
        return _database_unavailable()
