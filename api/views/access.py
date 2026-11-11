from django.db import DatabaseError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .common import _json, _json_body, _require_persona, _row


@csrf_exempt
@require_http_methods(['POST'])
def validate_access(request):
    try:
        persona, error = _require_persona(request, {'ADMINISTRADOR', 'RECEPCIONISTA'})
        if error:
            return error
        body = _json_body(request)
        if body is None:
            return _json({'error': 'El cuerpo de la solicitud debe ser JSON válido.'}, 400)
        try:
            access_point_id = int(body.get('punto_acceso_id'))
        except (ValueError, TypeError):
            return _json({'error': 'Indica un punto de acceso válido.'}, 400)
        receptionist_installation_id = None
        if 'RECEPCIONISTA' in persona['roles'] and 'ADMINISTRADOR' not in persona['roles']:
            receptionist_installation_id = persona.get('recepcionista_instalacion_id')
            if receptionist_installation_id is None:
                return _json({'error': 'Tu cuenta de recepción todavía no tiene una sede asignada.'}, 403)
        access_point = _row(
            'SELECT pa.punto_acceso_id, pa.instalacion_id, pa.uso, i.tiene_estacionamiento '
            'FROM punto_acceso pa JOIN instalacion i USING (instalacion_id) '
            'WHERE pa.punto_acceso_id = %s AND pa.activo AND i.activa',
            (access_point_id,),
        )
        if access_point is None:
            return _json({'error': 'El punto de acceso no existe o está inactivo.'}, 400)
        if access_point['uso'] == 'ESTACIONAMIENTO' and not access_point['tiene_estacionamiento']:
            return _json({'error': 'El punto de estacionamiento no está disponible porque la sede no cuenta con estacionamiento.'}, 400)
        if receptionist_installation_id is not None \
                and access_point['instalacion_id'] != receptionist_installation_id:
            return _json({'error': 'Solo puedes validar accesos en la sede asignada a tu cuenta.'}, 403)
        token = str(body.get('credential', '')).strip()
        event_type = str(body.get('tipo', '')).upper()
        if event_type not in {'ENTRADA', 'SALIDA'}:
            return _json({'error': 'El tipo debe ser ENTRADA o SALIDA.'}, 400)
        if token.startswith('FITLIFE-STAFF:'):
            result = _row(
                'SELECT evento_id, resultado, motivo_rechazo '
                'FROM registrar_acceso_personal_qr(%s, %s, %s::tipo_evento_acceso)',
                (token.removeprefix('FITLIFE-STAFF:'), access_point_id, event_type),
            )
        else:
            result = _row(
                'SELECT evento_id, resultado, motivo_rechazo '
                'FROM registrar_acceso_qr(%s, %s, %s::tipo_evento_acceso)',
                (token, access_point_id, event_type),
            )
        return _json(result)
    except DatabaseError:
        return _json({'error': 'No fue posible validar el QR. Revisa el punto de acceso y la configuración de FitLife.'}, 409)
