import logging
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from transbank.error.transbank_error import TransbankError

from .common import _database_unavailable, _execute, _json, _json_body, _require_persona, _row, _rows
from ..transbank import webpay_transaction


logger = logging.getLogger(__name__)

PLAN_FIELDS = {
    'tipo', 'nombre', 'descripcion', 'duracion_dias', 'precio_referencia',
    'incluye_entrenador_personal', 'incluye_lockers', 'incluye_estacionamiento', 'otros_beneficios',
    'acceso_todas_sedes', 'es_prueba_gratuita',
}


def _plan_values(body, partial=False):
    unknown = set(body) - PLAN_FIELDS - {'instalaciones_ids'}
    if unknown:
        raise ValueError('La solicitud contiene campos que no se pueden modificar.')
    values = {}
    if 'tipo' in body or not partial:
        plan_type = body.get('tipo')
        if not isinstance(plan_type, str) or plan_type not in {'PLAN', 'MEMBRESIA'}:
            raise ValueError('Selecciona el tipo Plan o Membresía.')
        values['tipo'] = plan_type
    if 'nombre' in body or not partial:
        name = str(body.get('nombre', '')).strip()
        if not name or len(name) > 80:
            raise ValueError('El nombre del plan es obligatorio y no puede superar 80 caracteres.')
        values['nombre'] = name
    if 'descripcion' in body or not partial:
        values['descripcion'] = str(body.get('descripcion', '')).strip() or None
    if 'duracion_dias' in body or not partial:
        raw_duration = body.get('duracion_dias')
        if isinstance(raw_duration, bool) or not (
            isinstance(raw_duration, int)
            or isinstance(raw_duration, str)
            and raw_duration.isascii()
            and raw_duration.isdecimal()
        ):
            raise ValueError('Indica una duración válida.')
        duration = int(raw_duration)
        if duration < 1:
            raise ValueError('La duración debe ser de al menos un día.')
        values['duracion_dias'] = duration
    if 'precio_referencia' in body or not partial:
        try:
            price = Decimal(str(body.get('precio_referencia', '')))
        except (ValueError, TypeError, InvalidOperation):
            raise ValueError('Indica un precio válido.') from None
        if not price.is_finite() or price < 0:
            raise ValueError('El precio debe ser un valor no negativo.')
        values['precio_referencia'] = price
    for field in ('incluye_entrenador_personal', 'incluye_lockers', 'incluye_estacionamiento'):
        if field in body or not partial:
            value = body.get(field, False)
            if not isinstance(value, bool):
                raise ValueError(f'El campo {field} debe ser verdadero o falso.')
            values[field] = value
    if 'otros_beneficios' in body or not partial:
        benefits = body.get('otros_beneficios', '')
        if not isinstance(benefits, str) or len(benefits) > 1000:
            raise ValueError('Los beneficios adicionales no pueden superar 1000 caracteres.')
        lines = [line.strip() for line in benefits.splitlines() if line.strip()]
        if len(lines) > 10 or any(len(line) > 100 for line in lines):
            raise ValueError('Indica hasta 10 beneficios, con un máximo de 100 caracteres cada uno.')
        values['otros_beneficios'] = '\n'.join(lines)
    for field in ('acceso_todas_sedes', 'es_prueba_gratuita'):
        if field in body or not partial:
            value = body.get(field, False)
            if not isinstance(value, bool):
                raise ValueError(f'El campo {field} debe ser verdadero o falso.')
            values[field] = value
    effective = dict(body)
    effective.update(values)
    if effective.get('es_prueba_gratuita'):
        if effective.get('precio_referencia', 0) != 0:
            raise ValueError('Una prueba gratuita debe tener precio cero.')
        if effective.get('acceso_todas_sedes'):
            raise ValueError('La prueba gratuita se configura por sede y no puede tener acceso global.')
    if effective.get('acceso_todas_sedes') and effective.get('tipo') != 'MEMBRESIA':
        raise ValueError('El acceso global solo está disponible para planes de tipo Membresía.')
    return values


def _plan_installations(body, plan_values=None):
    plan_values = plan_values or body
    if plan_values.get('acceso_todas_sedes'):
        return []
    raw_installation_ids = body.get('instalaciones_ids')
    if not isinstance(raw_installation_ids, list) or not raw_installation_ids:
        raise ValueError('Selecciona al menos una sede para publicar el plan.')
    if any(
        isinstance(installation_id, bool)
        or not isinstance(installation_id, int)
        and not (
            isinstance(installation_id, str)
            and installation_id.isascii()
            and installation_id.isdecimal()
        )
        for installation_id in raw_installation_ids
    ):
        raise ValueError('Selecciona sedes válidas para el plan.')
    installation_ids = sorted({int(installation_id) for installation_id in raw_installation_ids})
    if any(installation_id < 1 for installation_id in installation_ids):
        raise ValueError('Selecciona sedes válidas para el plan.')
    if plan_values.get('es_prueba_gratuita') and len(installation_ids) != 1:
        raise ValueError('Una prueba gratuita debe configurarse para exactamente una sede.')
    active_installations = {
        row['instalacion_id'] for row in _rows(
            'SELECT instalacion_id FROM instalacion '
            'WHERE activa AND instalacion_id = ANY(%s)',
            (installation_ids,),
        )
    }
    if active_installations != set(installation_ids):
        raise ValueError('Una o más sedes no están disponibles.')
    return installation_ids


def _replace_plan_installations(plan_id, installation_ids):
    _execute('DELETE FROM instalacion_plan WHERE plan_id = %s', (plan_id,))
    for installation_id in installation_ids:
        _execute(
            'INSERT INTO instalacion_plan (instalacion_id, plan_id) VALUES (%s, %s)',
            (installation_id, plan_id),
        )


def _save_plan(values, plan_id=None):
    if plan_id is None:
        columns = ', '.join(values)
        placeholders = ', '.join(['%s'] * len(values))
        return _execute(
            f'INSERT INTO plan_membresia ({columns}) VALUES ({placeholders}) RETURNING plan_id',
            list(values.values()),
        )[0]
    assignments = ', '.join(f'{column} = %s' for column in values)
    result = _execute(
        f'UPDATE plan_membresia SET {assignments} WHERE plan_id = %s AND activo '
        'RETURNING plan_id',
        [*values.values(), plan_id],
    )
    return result[0] if result else None


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def plans(request):
    try:
        if request.method == 'GET':
            return _json({'plans': _rows(
                'SELECT plan_id, tipo, nombre, descripcion, duracion_dias, precio_referencia, '
                'incluye_entrenador_personal, incluye_lockers, incluye_estacionamiento, otros_beneficios, '
                'acceso_todas_sedes, es_prueba_gratuita, '
                'ARRAY(SELECT i.nombre FROM instalacion i WHERE i.activa AND (pm.acceso_todas_sedes OR EXISTS ('
                'SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id)) ORDER BY i.nombre) AS sedes '
                'FROM plan_membresia pm WHERE pm.activo AND (pm.acceso_todas_sedes OR EXISTS ('
                'SELECT 1 FROM instalacion_plan ip JOIN instalacion i USING (instalacion_id) '
                'WHERE ip.plan_id = pm.plan_id AND i.activa)) ORDER BY pm.precio_referencia'
            )})
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        values = _plan_values(body)
        installation_ids = _plan_installations(body, values)
        with transaction.atomic():
            plan_id = _save_plan(values)
            _replace_plan_installations(plan_id, installation_ids)
        return _json({'plan_id': plan_id, 'message': 'Plan creado.'}, 201)
    except ValueError as error:
        return _json({'error': str(error)}, 400)
    except IntegrityError:
        return _json({'error': 'Ya existe un plan con ese nombre.'}, 409)
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['PATCH', 'DELETE'])
def plan_detail(request, plan_id):
    try:
        _, error = _require_persona(request, {'ADMINISTRADOR'})
        if error:
            return error
        if request.method == 'DELETE':
            result = _execute(
                'UPDATE plan_membresia SET activo = FALSE '
                'WHERE plan_id = %s AND activo RETURNING plan_id',
                (plan_id,),
            )
            if result is None:
                return _json({'error': 'Plan no encontrado o ya desactivado.'}, 404)
            return _json({'message': 'Plan desactivado.'})
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        current_plan = _row(
            'SELECT tipo, precio_referencia, acceso_todas_sedes, es_prueba_gratuita '
            'FROM plan_membresia WHERE plan_id = %s AND activo',
            (plan_id,),
        )
        if current_plan is None:
            return _json({'error': 'Plan no encontrado o ya desactivado.'}, 404)
        validation_body = {**current_plan, **body}
        values = _plan_values(validation_body, partial=True)
        if not values and 'instalaciones_ids' not in body:
            return _json({'error': 'Indica al menos un campo para actualizar.'}, 400)
        effective_plan = {**current_plan, **values}
        installation_ids = _plan_installations(body, effective_plan)
        with transaction.atomic():
            if values:
                result = _save_plan(values, plan_id)
            else:
                plan = _row(
                    'SELECT plan_id FROM plan_membresia WHERE plan_id = %s AND activo',
                    (plan_id,),
                )
                result = plan['plan_id'] if plan else None
            if result is not None:
                _replace_plan_installations(result, installation_ids)
        if result is None:
            return _json({'error': 'Plan no encontrado o ya desactivado.'}, 404)
        return _json({'plan_id': result, 'message': 'Plan actualizado.'})
    except ValueError as error:
        return _json({'error': str(error)}, 400)
    except IntegrityError:
        return _json({'error': 'Ya existe un plan con ese nombre.'}, 409)
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['POST'])
def create_membership(request):
    return _json({
        'error': 'La asignación manual de membresías está deshabilitada. El socio debe contratar un plan disponible en una sede.',
    }, 405)


def _webpay_return_url(request):
    return settings.WEBPAY_RETURN_URL or request.build_absolute_uri(
        reverse('api-webpay-return')
    )


def _mark_webpay_payment_failed(payment_id, membership_id):
    with transaction.atomic():
        _execute(
            "UPDATE pago SET estado = 'RECHAZADO', procesado_en = CURRENT_TIMESTAMP "
            "WHERE pago_id = %s AND estado = 'PENDIENTE'",
            (payment_id,),
        )
        _execute(
            "UPDATE membresia SET estado = 'CANCELADA' "
            "WHERE membresia_id = %s AND estado = 'PENDIENTE'",
            (membership_id,),
        )


@csrf_exempt
@require_http_methods(['POST'])
def purchase_membership(request):
    try:
        persona, error = _require_persona(request, {'SOCIO'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        if set(body) - {'plan_id', 'instalacion_id', 'metodo_pago'}:
            return _json({'error': 'La solicitud contiene campos que no se pueden modificar.'}, 400)
        if body.get('metodo_pago') != 'WEBPAY':
            return _json({
                'error': 'Elige débito o crédito en Webpay. No se acepta efectivo.',
            }, 400)
        raw_plan_id = body.get('plan_id')
        if isinstance(raw_plan_id, bool) or not (
            isinstance(raw_plan_id, int)
            or isinstance(raw_plan_id, str) and raw_plan_id.isascii() and raw_plan_id.isdecimal()
        ):
            return _json({'error': 'Selecciona un plan válido.'}, 400)
        plan_id = int(raw_plan_id)
        if plan_id < 1:
            return _json({'error': 'Selecciona un plan válido.'}, 400)
        raw_installation_id = body.get('instalacion_id')
        if isinstance(raw_installation_id, bool) or not (
            isinstance(raw_installation_id, int)
            or isinstance(raw_installation_id, str)
            and raw_installation_id.isascii()
            and raw_installation_id.isdecimal()
        ):
            return _json({'error': 'Selecciona una sede válida.'}, 400)
        installation_id = int(raw_installation_id)
        if installation_id < 1:
            return _json({'error': 'Selecciona una sede válida.'}, 400)

        with transaction.atomic():
            member = _row(
                'SELECT socio_id FROM socio WHERE rut = %s AND activo FOR UPDATE',
                (persona['rut'],),
            )
            plan = _row(
                'SELECT pm.plan_id, pm.duracion_dias, pm.precio_referencia, pm.acceso_todas_sedes '
                'FROM plan_membresia pm JOIN instalacion i ON i.instalacion_id = %s '
                'WHERE pm.plan_id = %s AND pm.activo AND i.activa AND NOT pm.es_prueba_gratuita '
                'AND (pm.acceso_todas_sedes OR EXISTS ('
                'SELECT 1 FROM instalacion_plan ip WHERE ip.plan_id = pm.plan_id '
                'AND ip.instalacion_id = i.instalacion_id))',
                (installation_id, plan_id),
            )
            if member is None or plan is None:
                return _json({'error': 'No encontramos tu cuenta activa o el plan en la sede seleccionada.'}, 404)
            current = _row(
                "SELECT m.membresia_id FROM membresia m "
                "JOIN plan_membresia pm USING (plan_id) WHERE m.socio_id = %s "
                "AND m.estado IN ('ACTIVA', 'CONGELADA', 'PENDIENTE') "
                "AND (m.estado = 'PENDIENTE' OR m.fecha_fin IS NULL OR m.fecha_fin >= CURRENT_DATE) "
                "AND (m.instalacion_id = %s OR pm.acceso_todas_sedes OR %s) "
                "FOR UPDATE OF m",
                (member['socio_id'], installation_id, plan.get('acceso_todas_sedes', False)),
            )
            if current:
                return _json({'error': 'Ya tienes una membresía vigente o pendiente que no se puede combinar con este plan.'}, 409)

            amount = Decimal(str(plan['precio_referencia']))
            if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
                return _json({'error': 'El precio del plan debe ser un monto válido en pesos chilenos.'}, 409)

            if amount == 0:
                membership = _execute(
                    "INSERT INTO membresia (socio_id, plan_id, instalacion_id, estado, fecha_inicio, fecha_fin, precio_acordado) "
                    "VALUES (%s, %s, %s, 'ACTIVA', NULL, NULL, 0) RETURNING membresia_id",
                    (member['socio_id'], plan_id, installation_id),
                )
                return _json({
                    'membresia_id': membership[0],
                    'gratis': True,
                    'message': 'Plan activado correctamente.',
                }, 201)

            membership = _execute(
                "INSERT INTO membresia (socio_id, plan_id, instalacion_id, estado, fecha_inicio, fecha_fin, precio_acordado) "
                "VALUES (%s, %s, %s, 'PENDIENTE', NULL, NULL, %s) RETURNING membresia_id",
                (member['socio_id'], plan_id, installation_id, amount),
            )
            payment = _execute(
                "INSERT INTO pago (membresia_id, metodo, estado, monto) "
                "VALUES (%s, 'WEBPAY'::metodo_pago, 'PENDIENTE', %s) RETURNING pago_id",
                (membership[0], amount),
            )
            buy_order = f"FL{payment[0]:020d}"

        try:
            response = webpay_transaction().create(
                buy_order,
                str(member['socio_id']),
                int(amount),
                _webpay_return_url(request),
            )
            if not response.get('token') or not response.get('url'):
                raise TransbankError('Transbank no devolvió los datos de redirección.')
            saved_payment = _execute(
                "UPDATE pago SET referencia_externa = %s "
                "WHERE pago_id = %s AND estado = 'PENDIENTE' RETURNING pago_id",
                (response['token'], payment[0]),
            )
            if saved_payment is None:
                raise TransbankError('No fue posible guardar la referencia del pago.')
        except (TransbankError, requests.RequestException, RuntimeError) as error:
            logger.exception('No se pudo iniciar el pago Webpay para la membresía %s.', membership[0])
            _mark_webpay_payment_failed(payment[0], membership[0])
            return _json({
                'error': 'No se pudo iniciar el pago con Webpay. Inténtalo nuevamente.',
            }, 502)
        return _json({
            'membresia_id': membership[0],
            'url': response['url'],
            'token': response['token'],
        }, 201)
    except IntegrityError:
        return _json({'error': 'No fue posible iniciar la compra. Revisa si ya tienes una membresía pendiente.'}, 409)
    except DatabaseError:
        return _database_unavailable()


@csrf_exempt
@require_http_methods(['POST'])
def redeem_free_trial(request):
    try:
        persona, error = _require_persona(request, {'SOCIO'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        if set(body) != {'plan_id', 'instalacion_id'}:
            return _json({'error': 'Selecciona la prueba gratuita y su sede.'}, 400)
        raw_plan_id = body.get('plan_id')
        if isinstance(raw_plan_id, bool) or not (
            isinstance(raw_plan_id, int)
            or isinstance(raw_plan_id, str)
            and raw_plan_id.isascii()
            and raw_plan_id.isdecimal()
        ):
            return _json({'error': 'Selecciona una prueba gratuita válida.'}, 400)
        plan_id = int(raw_plan_id)
        if plan_id < 1:
            return _json({'error': 'Selecciona una prueba gratuita válida.'}, 400)
        raw_installation_id = body.get('instalacion_id')
        if isinstance(raw_installation_id, bool) or not (
            isinstance(raw_installation_id, int)
            or isinstance(raw_installation_id, str)
            and raw_installation_id.isascii()
            and raw_installation_id.isdecimal()
        ):
            return _json({'error': 'Selecciona una sede válida.'}, 400)
        installation_id = int(raw_installation_id)
        if installation_id < 1:
            return _json({'error': 'Selecciona una sede válida.'}, 400)

        with transaction.atomic():
            member = _row(
                'SELECT socio_id FROM socio WHERE rut = %s AND activo FOR UPDATE',
                (persona['rut'],),
            )
            if member is None:
                return _json({'error': 'No encontramos tu perfil de socio activo.'}, 404)
            already_redeemed = _row(
                'SELECT rut FROM prueba_socio WHERE rut = %s FOR UPDATE',
                (persona['rut'],),
            )
            if already_redeemed:
                return _json({'error': 'Ya canjeaste la prueba gratuita disponible para tu cuenta.'}, 409)

            offer = _row(
                'SELECT pm.plan_id, pm.duracion_dias, pm.precio_referencia '
                'FROM plan_membresia pm '
                'JOIN instalacion_plan ip USING (plan_id) '
                'JOIN instalacion i USING (instalacion_id) '
                'WHERE pm.plan_id = %s AND ip.instalacion_id = %s AND pm.activo AND i.activa '
                'AND pm.es_prueba_gratuita AND NOT pm.acceso_todas_sedes '
                'AND pm.precio_referencia = 0 FOR UPDATE OF pm',
                (plan_id, installation_id),
            )
            if offer is None:
                return _json({'error': 'No hay una prueba gratuita activa en la sede seleccionada.'}, 404)

            current = _row(
                "SELECT m.membresia_id FROM membresia m "
                "JOIN plan_membresia pm USING (plan_id) "
                "WHERE m.socio_id = %s AND m.estado IN ('ACTIVA', 'CONGELADA', 'PENDIENTE') "
                "AND (m.estado = 'PENDIENTE' OR m.fecha_fin IS NULL OR m.fecha_fin >= CURRENT_DATE) "
                "AND (m.instalacion_id = %s OR pm.acceso_todas_sedes) FOR UPDATE OF m",
                (member['socio_id'], installation_id),
            )
            if current:
                return _json({'error': 'Ya tienes una membresía vigente o pendiente que cubre esta sede.'}, 409)

            membership = _execute(
                "INSERT INTO membresia (socio_id, plan_id, instalacion_id, estado, "
                "fecha_inicio, fecha_fin, precio_acordado) "
                "VALUES (%s, %s, %s, 'ACTIVA', CURRENT_DATE, "
                "CURRENT_DATE + %s - 1, 0) RETURNING membresia_id",
                (member['socio_id'], offer['plan_id'], installation_id, offer['duracion_dias']),
            )
            _execute(
                'INSERT INTO prueba_socio (rut, membresia_id) VALUES (%s, %s)',
                (persona['rut'], membership[0]),
            )
        return _json({
            'membresia_id': membership[0],
            'message': 'Tu prueba gratuita fue activada.',
        }, 201)
    except IntegrityError:
        return _json({'error': 'Ya canjeaste la prueba gratuita o tienes una membresía vigente en esta sede.'}, 409)
    except DatabaseError:
        return _database_unavailable()


def _payment_redirect(status):
    return HttpResponseRedirect(f"/panel/?pago={status}")


def _webpay_payment_id(buy_order):
    if not isinstance(buy_order, str) or len(buy_order) != 22 or not buy_order.startswith('FL'):
        return None
    digits = buy_order[2:]
    return int(digits) if digits.isdigit() else None


def _cancel_webpay_order(buy_order, token):
    payment_id = _webpay_payment_id(buy_order)
    if payment_id is None:
        return
    with transaction.atomic():
        payment = _row(
            "SELECT pago_id, membresia_id FROM pago WHERE pago_id = %s "
            "AND referencia_externa = %s AND metodo = 'WEBPAY'::metodo_pago "
            "AND estado = 'PENDIENTE' FOR UPDATE",
            (payment_id, token),
        )
        if payment is None:
            return
        _execute(
            "UPDATE pago SET estado = 'RECHAZADO', procesado_en = CURRENT_TIMESTAMP "
            "WHERE pago_id = %s",
            (payment['pago_id'],),
        )
        _execute(
            "UPDATE membresia SET estado = 'CANCELADA' "
            "WHERE membresia_id = %s AND estado = 'PENDIENTE'",
            (payment['membresia_id'],),
        )


@csrf_exempt
@require_http_methods(['POST'])
def webpay_return(request):
    try:
        cancelled_token = request.POST.get('TBK_TOKEN')
        if cancelled_token:
            buy_order = request.POST.get('TBK_ORDEN_COMPRA')
            try:
                status = webpay_transaction().status(cancelled_token)
            except (TransbankError, requests.RequestException, RuntimeError):
                logger.exception('No se pudo verificar el estado del pago cancelado en Webpay.')
                return _payment_redirect('verificacion')
            if status.get('buy_order') != buy_order or status.get('status') == 'AUTHORIZED':
                logger.error('El retorno de cancelación de Webpay no coincide con la orden esperada.')
                return _payment_redirect('verificacion')
            _cancel_webpay_order(buy_order, cancelled_token)
            return _payment_redirect('cancelado')
        token = request.POST.get('token_ws')
        if not token:
            return _payment_redirect('sin-confirmar')

        pending_payment = _row(
            "SELECT pago_id, estado FROM pago WHERE referencia_externa = %s "
            "AND metodo = 'WEBPAY'::metodo_pago",
            (token,),
        )
        if pending_payment is None:
            logger.error('Se recibió un token Webpay sin un pago FitLife asociado.')
            return _payment_redirect('verificacion')
        if pending_payment['estado'] == 'APROBADO':
            return _payment_redirect('aprobado')
        if pending_payment['estado'] != 'PENDIENTE':
            return _payment_redirect('rechazado')
        expected_buy_order = f"FL{pending_payment['pago_id']:020d}"

        try:
            result = webpay_transaction().commit(token)
        except (TransbankError, requests.RequestException, RuntimeError):
            logger.warning('No se pudo confirmar con commit; consultando el estado Webpay.', exc_info=True)
            try:
                result = webpay_transaction().status(token)
            except (TransbankError, requests.RequestException, RuntimeError):
                logger.exception('Transbank no pudo confirmar una transacción de membresía.')
                return _payment_redirect('verificacion')

        buy_order = result.get('buy_order')
        if buy_order != expected_buy_order:
            logger.error('La confirmación Webpay no incluyó el número de orden.')
            return _payment_redirect('verificacion')

        with transaction.atomic():
            payment = _row(
                'SELECT p.pago_id, p.membresia_id, p.monto, p.estado, '
                'm.precio_acordado, m.estado AS membresia_estado FROM pago p '
                'JOIN membresia m USING (membresia_id) '
                'WHERE p.pago_id = %s AND p.referencia_externa = %s '
                'AND p.metodo = %s::metodo_pago '
                'FOR UPDATE OF p, m',
                (pending_payment['pago_id'], token, 'WEBPAY'),
            )
            if payment is None:
                logger.error('La orden Webpay %s no coincide con un pago FitLife.', buy_order)
                return _payment_redirect('verificacion')
            if payment['estado'] == 'APROBADO':
                return _payment_redirect('aprobado')
            if payment['estado'] != 'PENDIENTE':
                return _payment_redirect('rechazado')
            if payment['membresia_estado'] != 'PENDIENTE':
                logger.error('El pago Webpay está pendiente, pero su membresía no.')
                return _payment_redirect('verificacion')

            try:
                confirmed_amount = Decimal(str(result.get('amount')))
            except (InvalidOperation, TypeError, ValueError):
                confirmed_amount = None
            transaction_approved = (
                result.get('status') == 'AUTHORIZED'
                and result.get('response_code') == 0
            )
            amount_matches = (
                confirmed_amount == Decimal(str(payment['monto']))
                and confirmed_amount == Decimal(str(payment['precio_acordado']))
            )
            if transaction_approved and not amount_matches:
                logger.error('El monto confirmado por Webpay no coincide con la orden %s.', buy_order)
                return _payment_redirect('verificacion')
            if not transaction_approved:
                _execute(
                    "UPDATE pago SET estado = 'RECHAZADO', procesado_en = CURRENT_TIMESTAMP "
                    'WHERE pago_id = %s',
                    (payment['pago_id'],),
                )
                _execute(
                    "UPDATE membresia SET estado = 'CANCELADA' "
                    "WHERE membresia_id = %s AND estado = 'PENDIENTE'",
                    (payment['membresia_id'],),
                )
                return _payment_redirect('rechazado')

            _execute(
                "UPDATE pago SET estado = 'APROBADO', procesado_en = CURRENT_TIMESTAMP "
                'WHERE pago_id = %s AND estado = %s',
                (payment['pago_id'], 'PENDIENTE'),
            )
            _execute(
                "UPDATE membresia SET estado = 'ACTIVA' "
                "WHERE membresia_id = %s AND estado = 'PENDIENTE'",
                (payment['membresia_id'],),
            )
        return _payment_redirect('aprobado')
    except DatabaseError:
        logger.exception('No se pudo guardar el resultado del pago Webpay.')
        return _payment_redirect('verificacion')
