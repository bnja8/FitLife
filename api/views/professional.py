from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import DatabaseError, IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .common import (
    _database_unavailable, _execute, _json, _json_body, _profile_ids,
    _require_persona, _row, _rows,
)


def _professional_context(request):
    persona, error = _require_persona(request, {'INSTRUCTOR'})
    if error:
        return None, None, error
    ids = _profile_ids(persona['rut'])
    instructor_id = ids['instructor_id'] if ids else None
    profile = _row(
        'SELECT pi.tipo FROM perfil_instructor pi JOIN instructor i USING (instructor_id) '
        'WHERE pi.instructor_id = %s AND pi.activo AND i.activo',
        (instructor_id,),
    ) if instructor_id else None
    if not profile:
        return None, None, _json({'error': 'No tienes un perfil profesional activo.'}, 403)
    return instructor_id, profile['tipo'], None


def _workspace(instructor_id, specialty):
    members = _rows(
        'SELECT s.socio_id, p.nombres || %s || p."apellidoPaterno" AS nombre '
        'FROM instructor_socio asignacion JOIN socio s USING (socio_id) '
        'JOIN persona p ON p.rut = s.rut '
        'WHERE asignacion.instructor_id = %s AND asignacion.activo AND s.activo '
        'ORDER BY nombre',
        (' ', instructor_id),
    )
    data = {'specialty': specialty, 'assigned_members': members}
    if specialty == 'PERSONAL_TRAINER':
        plans = _rows(
            'SELECT pl.plan_id, pl.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
            'pl.titulo, pl.objetivo, pl.fecha_inicio, pl.fecha_fin, pl.observaciones, pl.creado_en '
            'FROM plan_entrenamiento pl JOIN socio s USING (socio_id) '
            'JOIN persona p ON p.rut = s.rut WHERE pl.instructor_id = %s '
            'AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
            'WHERE asignacion.instructor_id = pl.instructor_id AND asignacion.socio_id = pl.socio_id '
            'AND asignacion.activo) '
            'ORDER BY pl.creado_en DESC LIMIT 100',
            (' ', instructor_id),
        )
        routines = _rows(
            'SELECT ru.rutina_id, ru.plan_id, ru.dia FROM rutina_entrenamiento ru '
            'JOIN plan_entrenamiento pl USING (plan_id) WHERE pl.instructor_id = %s '
            'AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
            'WHERE asignacion.instructor_id = pl.instructor_id AND asignacion.socio_id = pl.socio_id '
            'AND asignacion.activo) '
            'ORDER BY ru.plan_id, ru.orden',
            (instructor_id,),
        )
        exercises = _rows(
            'SELECT ex.rutina_id, ex.nombre, ex.series, ex.repeticiones, ex.carga_kg, '
            'ex.descanso_segundos, ex.duracion_segundos, ex.observaciones '
            'FROM ejercicio_entrenamiento ex JOIN rutina_entrenamiento ru USING (rutina_id) '
            'JOIN plan_entrenamiento pl USING (plan_id) WHERE pl.instructor_id = %s '
            'AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
            'WHERE asignacion.instructor_id = pl.instructor_id AND asignacion.socio_id = pl.socio_id '
            'AND asignacion.activo) '
            'ORDER BY ex.ejercicio_id',
            (instructor_id,),
        )
        for routine in routines:
            routine['ejercicios'] = [
                exercise for exercise in exercises
                if exercise['rutina_id'] == routine['rutina_id']
            ]
        for plan in plans:
            plan['rutinas'] = [routine for routine in routines if routine['plan_id'] == plan['plan_id']]
        data.update(
            evaluations=_rows(
                'SELECT e.evaluacion_id, e.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
                'e.objetivo, e.condicion_inicial, e.antecedentes, e.evaluada_en '
                'FROM evaluacion_inicial_personal e JOIN socio s USING (socio_id) '
                'JOIN persona p ON p.rut = s.rut WHERE e.instructor_id = %s '
                'AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
                'WHERE asignacion.instructor_id = e.instructor_id AND asignacion.socio_id = e.socio_id '
                'AND asignacion.activo) '
                'ORDER BY e.evaluada_en DESC LIMIT 100',
                (' ', instructor_id),
            ),
            plans=plans,
            sessions=_rows(
                'SELECT se.sesion_personal_id, se.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
                'se.plan_id, se.realizada_en, se.duracion_minutos, se.observaciones '
                'FROM sesion_entrenamiento_personal se JOIN socio s USING (socio_id) '
                'JOIN persona p ON p.rut = s.rut WHERE se.instructor_id = %s '
                'AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
                'WHERE asignacion.instructor_id = se.instructor_id AND asignacion.socio_id = se.socio_id '
                'AND asignacion.activo) '
                'ORDER BY se.realizada_en DESC LIMIT 100',
                (' ', instructor_id),
            ),
            progress=_rows(
                'SELECT pr.progreso_id, pr.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
                'pr.objetivo, pr.progreso, pr.observaciones, pr.registrado_en '
                'FROM progreso_entrenamiento_personal pr JOIN socio s USING (socio_id) '
                'JOIN persona p ON p.rut = s.rut WHERE pr.instructor_id = %s '
                'AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
                'WHERE asignacion.instructor_id = pr.instructor_id AND asignacion.socio_id = pr.socio_id '
                'AND asignacion.activo) '
                'ORDER BY pr.registrado_en DESC LIMIT 100',
                (' ', instructor_id),
            ),
        )
    elif specialty == 'COACH':
        data.update(
            goals=_rows(
                'SELECT o.objetivo_id, o.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
                'o.titulo, o.descripcion, o.fecha_objetivo, o.asistencias_semanales, o.estado, o.creado_en '
                'FROM objetivo_coaching o JOIN socio s USING (socio_id) JOIN persona p ON p.rut = s.rut '
                'WHERE o.instructor_id = %s AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
                'WHERE asignacion.instructor_id = o.instructor_id AND asignacion.socio_id = o.socio_id '
                'AND asignacion.activo) ORDER BY o.creado_en DESC LIMIT 100',
                (' ', instructor_id),
            ),
            sessions=_rows(
                'SELECT sc.sesion_coaching_id, sc.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
                'sc.objetivo_id, sc.realizada_en, sc.compromisos, sc.adherencia, sc.observaciones '
                'FROM sesion_coaching sc JOIN socio s USING (socio_id) JOIN persona p ON p.rut = s.rut '
                'WHERE sc.instructor_id = %s AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
                'WHERE asignacion.instructor_id = sc.instructor_id AND asignacion.socio_id = sc.socio_id '
                'AND asignacion.activo) ORDER BY sc.realizada_en DESC LIMIT 100',
                (' ', instructor_id),
            ),
        )
    elif specialty == 'PREPARADOR_FISICO':
        data.update(
            evaluations=_rows(
                'SELECT e.evaluacion_fisica_id, e.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
                'e.prueba, e.capacidad, e.resultado, e.unidad, e.evaluada_en, e.observaciones '
                'FROM evaluacion_fisica e JOIN socio s USING (socio_id) JOIN persona p ON p.rut = s.rut '
                'WHERE e.instructor_id = %s AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
                'WHERE asignacion.instructor_id = e.instructor_id AND asignacion.socio_id = e.socio_id '
                'AND asignacion.activo) ORDER BY e.evaluada_en DESC LIMIT 100',
                (' ', instructor_id),
            ),
            plans=_rows(
                'SELECT pl.planificacion_id, pl.socio_id, p.nombres || %s || p."apellidoPaterno" AS socio, '
                'pl.titulo, pl.objetivo, pl.etapa, pl.fecha_inicio, pl.fecha_fin, pl.volumen_semanal, '
                'pl.intensidad, pl.observaciones, pl.creado_en '
                'FROM planificacion_fisica pl JOIN socio s USING (socio_id) JOIN persona p ON p.rut = s.rut '
                'WHERE pl.instructor_id = %s AND EXISTS (SELECT 1 FROM instructor_socio asignacion '
                'WHERE asignacion.instructor_id = pl.instructor_id AND asignacion.socio_id = pl.socio_id '
                'AND asignacion.activo) ORDER BY pl.creado_en DESC LIMIT 100',
                (' ', instructor_id),
            ),
        )
    return data


def _string(body, name, label, maximum=3000, required=True):
    value = body.get(name)
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ValueError(f'El campo {label} no es válido.')
    value = value.strip()
    if required and not value:
        raise ValueError(f'El campo {label} es obligatorio.')
    if len(value) > maximum:
        raise ValueError(f'El campo {label} supera el largo permitido.')
    return value or None


def _number(body, name, label, minimum=None, maximum=None, optional=False):
    value = body.get(name)
    if optional and value in (None, ''):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo {label} debe ser un número entero.')
    if (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        raise ValueError(f'El campo {label} está fuera del rango permitido.')
    return number


def _date(body, name, label, optional=False):
    value = body.get(name)
    if optional and value in (None, ''):
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError(f'El campo {label} debe ser una fecha válida.')


def _decimal(body, name, label, optional=False):
    value = body.get(name)
    if optional and value in (None, ''):
        return None
    try:
        number = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        raise ValueError(f'El campo {label} debe ser un número válido.')
    if not number.is_finite() or number < 0:
        raise ValueError(f'El campo {label} no puede ser negativo.')
    return number


def _assignment_exists(instructor_id, member_id):
    return _row(
        'SELECT 1 AS asignado FROM instructor_socio asignacion '
        'JOIN socio s USING (socio_id) '
        'WHERE asignacion.instructor_id = %s AND asignacion.socio_id = %s '
        'AND asignacion.activo AND s.activo FOR UPDATE OF asignacion',
        (instructor_id, member_id),
    ) is not None


def _parse_exercises(exercises):
    if not isinstance(exercises, list) or not 1 <= len(exercises) <= 30:
        raise ValueError('Agrega entre 1 y 30 ejercicios a la rutina.')
    parsed = []
    for exercise in exercises:
        if not isinstance(exercise, dict):
            raise ValueError('La lista de ejercicios no es válida.')
        parsed.append((
            _string(exercise, 'nombre', 'nombre del ejercicio', 120),
            _number(exercise, 'series', 'series', 1, 100),
            _string(exercise, 'repeticiones', 'repeticiones', 40),
            _decimal(exercise, 'carga_kg', 'carga', optional=True),
            _number(exercise, 'descanso_segundos', 'descanso', 0, 86400, optional=True),
            _number(exercise, 'duracion_segundos', 'duración', 0, 86400, optional=True),
            _string(exercise, 'observaciones', 'observaciones', 1000, required=False),
        ))
    return parsed


def _parse_routines(body):
    routines = body.get('rutinas')
    if routines is None:
        routines = [{
            'dia': body.get('dia'),
            'ejercicios': body.get('ejercicios'),
        }]
    if not isinstance(routines, list) or not 1 <= len(routines) <= 14:
        raise ValueError('Agrega entre 1 y 14 días o bloques de rutina.')
    parsed = []
    seen_days = set()
    for routine in routines:
        if not isinstance(routine, dict):
            raise ValueError('La lista de rutinas no es válida.')
        day = _string(routine, 'dia', 'día de rutina', 40)
        if day.casefold() in seen_days:
            raise ValueError('Cada día o bloque de rutina debe ser único.')
        seen_days.add(day.casefold())
        parsed.append((day, _parse_exercises(routine.get('ejercicios'))))
    return parsed


def _create_record(body, instructor_id, specialty):
    action = body.get('accion')
    member_id = _number(body, 'socio_id', 'socio', 1)
    if not _assignment_exists(instructor_id, member_id):
        return _json({'error': 'El socio no está asignado a tu perfil profesional.'}, 403)

    if specialty == 'PERSONAL_TRAINER':
        if action == 'EVALUACION_INICIAL':
            objective = _string(body, 'objetivo', 'objetivo')
            condition = _string(body, 'condicion_inicial', 'condición inicial')
            background = _string(body, 'antecedentes', 'antecedentes', required=False)
            _execute(
                'INSERT INTO evaluacion_inicial_personal '
                '(instructor_id, socio_id, objetivo, condicion_inicial, antecedentes) '
                'VALUES (%s, %s, %s, %s, %s)',
                (instructor_id, member_id, objective, condition, background),
            )
        elif action == 'PLAN_ENTRENAMIENTO':
            title = _string(body, 'titulo', 'título', 120)
            objective = _string(body, 'objetivo', 'objetivo')
            start = _date(body, 'fecha_inicio', 'fecha de inicio')
            end = _date(body, 'fecha_fin', 'fecha de término', optional=True)
            if end and end < start:
                raise ValueError('La fecha de término debe ser posterior al inicio.')
            routines = _parse_routines(body)
            notes = _string(body, 'observaciones', 'observaciones', required=False)
            plan = _execute(
                'INSERT INTO plan_entrenamiento '
                '(instructor_id, socio_id, titulo, objetivo, fecha_inicio, fecha_fin, observaciones) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING plan_id',
                (instructor_id, member_id, title, objective, start, end, notes),
            )
            for order, (day, exercises) in enumerate(routines, start=1):
                routine = _execute(
                    'INSERT INTO rutina_entrenamiento (plan_id, dia, orden) '
                    'VALUES (%s, %s, %s) RETURNING rutina_id',
                    (plan[0], day, order),
                )
                for exercise in exercises:
                    _execute(
                        'INSERT INTO ejercicio_entrenamiento '
                        '(rutina_id, nombre, series, repeticiones, carga_kg, descanso_segundos, '
                        'duracion_segundos, observaciones) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
                        (routine[0], *exercise),
                    )
        elif action == 'SESION_ENTRENAMIENTO':
            plan_id = _number(body, 'plan_id', 'plan', 1, optional=True)
            if plan_id and not _row(
                'SELECT 1 AS permitido FROM plan_entrenamiento '
                'WHERE plan_id = %s AND instructor_id = %s AND socio_id = %s',
                (plan_id, instructor_id, member_id),
            ):
                return _json({'error': 'El plan no corresponde al socio seleccionado.'}, 403)
            duration = _number(body, 'duracion_minutos', 'duración', 1, 1440, optional=True)
            notes = _string(body, 'observaciones', 'observaciones', required=False)
            _execute(
                'INSERT INTO sesion_entrenamiento_personal '
                '(instructor_id, socio_id, plan_id, duracion_minutos, observaciones) '
                'VALUES (%s, %s, %s, %s, %s)',
                (instructor_id, member_id, plan_id, duration, notes),
            )
        elif action == 'PROGRESO':
            objective = _string(body, 'objetivo', 'objetivo')
            progress = _number(body, 'progreso', 'progreso', 0, 100)
            notes = _string(body, 'observaciones', 'observaciones', required=False)
            _execute(
                'INSERT INTO progreso_entrenamiento_personal '
                '(instructor_id, socio_id, objetivo, progreso, observaciones) VALUES (%s, %s, %s, %s, %s)',
                (instructor_id, member_id, objective, progress, notes),
            )
        else:
            return _json({'error': 'La operación no corresponde a Entrenador personal.'}, 400)
    elif specialty == 'COACH':
        if action == 'OBJETIVO':
            title = _string(body, 'titulo', 'título', 120)
            description = _string(body, 'descripcion', 'descripción', required=False)
            target_date = _date(body, 'fecha_objetivo', 'fecha objetivo', optional=True)
            weekly = _number(body, 'asistencias_semanales', 'asistencias semanales', 1, 7, optional=True)
            _execute(
                'INSERT INTO objetivo_coaching '
                '(instructor_id, socio_id, titulo, descripcion, fecha_objetivo, asistencias_semanales) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (instructor_id, member_id, title, description, target_date, weekly),
            )
        elif action == 'SESION_COACHING':
            objective_id = _number(body, 'objetivo_id', 'objetivo', 1, optional=True)
            if objective_id and not _row(
                'SELECT 1 AS permitido FROM objetivo_coaching '
                'WHERE objetivo_id = %s AND instructor_id = %s AND socio_id = %s',
                (objective_id, instructor_id, member_id),
            ):
                return _json({'error': 'El objetivo no corresponde al socio seleccionado.'}, 403)
            commitments = _string(body, 'compromisos', 'compromisos', required=False)
            adherence = _number(body, 'adherencia', 'adherencia', 0, 100, optional=True)
            notes = _string(body, 'observaciones', 'observaciones', required=False)
            _execute(
                'INSERT INTO sesion_coaching '
                '(instructor_id, socio_id, objetivo_id, compromisos, adherencia, observaciones) '
                'VALUES (%s, %s, %s, %s, %s, %s)',
                (instructor_id, member_id, objective_id, commitments, adherence, notes),
            )
        elif action == 'ESTADO_OBJETIVO':
            objective_id = _number(body, 'objetivo_id', 'objetivo', 1)
            status = body.get('estado')
            if status not in {'PENDIENTE', 'EN_CURSO', 'CUMPLIDO', 'PAUSADO'}:
                raise ValueError('Selecciona un estado de objetivo válido.')
            if not _row(
                'SELECT 1 AS permitido FROM objetivo_coaching '
                'WHERE objetivo_id = %s AND instructor_id = %s AND socio_id = %s',
                (objective_id, instructor_id, member_id),
            ):
                return _json({'error': 'El objetivo no corresponde al socio seleccionado.'}, 403)
            _execute(
                'UPDATE objetivo_coaching SET estado = %s '
                'WHERE objetivo_id = %s AND instructor_id = %s AND socio_id = %s '
                'RETURNING objetivo_id',
                (status, objective_id, instructor_id, member_id),
            )
        else:
            return _json({'error': 'La operación no corresponde a Coach.'}, 400)
    elif specialty == 'PREPARADOR_FISICO':
        if action == 'EVALUACION_FISICA':
            test = _string(body, 'prueba', 'prueba', 120)
            capacity = body.get('capacidad')
            if capacity not in {'RESISTENCIA', 'FUERZA', 'VELOCIDAD', 'FLEXIBILIDAD', 'COMPOSICION', 'OTRA'}:
                raise ValueError('Selecciona una capacidad física válida.')
            result = _decimal(body, 'resultado', 'resultado')
            unit = _string(body, 'unidad', 'unidad', 30)
            notes = _string(body, 'observaciones', 'observaciones', required=False)
            _execute(
                'INSERT INTO evaluacion_fisica '
                '(instructor_id, socio_id, prueba, capacidad, resultado, unidad, observaciones) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (instructor_id, member_id, test, capacity, result, unit, notes),
            )
        elif action == 'PLANIFICACION_FISICA':
            title = _string(body, 'titulo', 'título', 120)
            objective = _string(body, 'objetivo', 'objetivo')
            stage = _string(body, 'etapa', 'etapa', 80)
            start = _date(body, 'fecha_inicio', 'fecha de inicio')
            end = _date(body, 'fecha_fin', 'fecha de término', optional=True)
            if end and end < start:
                raise ValueError('La fecha de término debe ser posterior al inicio.')
            volume = _decimal(body, 'volumen_semanal', 'volumen', optional=True)
            intensity = _number(body, 'intensidad', 'intensidad', 1, 10, optional=True)
            notes = _string(body, 'observaciones', 'observaciones', required=False)
            _execute(
                'INSERT INTO planificacion_fisica '
                '(instructor_id, socio_id, titulo, objetivo, etapa, fecha_inicio, fecha_fin, '
                'volumen_semanal, intensidad, observaciones) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                (instructor_id, member_id, title, objective, stage, start, end, volume, intensity, notes),
            )
        else:
            return _json({'error': 'La operación no corresponde a Preparador físico.'}, 400)
    else:
        return _json({'error': 'Esta especialidad no puede guardar registros de entrenamiento.'}, 403)
    return _json({'message': 'Registro profesional guardado.'}, 201)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def professional_workspace(request):
    try:
        instructor_id, specialty, error = _professional_context(request)
        if error:
            return error
        if request.method == 'GET':
            return _json(_workspace(instructor_id, specialty))
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        with transaction.atomic():
            return _create_record(body, instructor_id, specialty)
    except ValueError as error:
        return _json({'error': str(error)}, 400)
    except IntegrityError:
        return _json({'error': 'No se pudo guardar el registro. Verifica las relaciones y los datos ingresados.'}, 409)
    except DatabaseError:
        return _database_unavailable()
