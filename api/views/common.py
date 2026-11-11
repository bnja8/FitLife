import json
import uuid
from io import BytesIO
from urllib.parse import urlsplit

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from PIL import Image, ImageOps, UnidentifiedImageError

from ..authentication import decode_token

MAX_CLASS_IMAGE_SIZE = 5 * 1024 * 1024


def dashboard_page(request):
    return render(request, 'views/html/dashboard.html')

def home_page(request):
    return render(request, 'views/html/home.html')

def gym_locations_page(request):
    return render(request, 'views/html/sedes.html')

def auth_page(request):
    return render(request, 'views/html/auth.html')

def _json_body(request):
    try:
        body = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None

def _prepare_class_image(upload):
    if upload is None:
        return None
    if upload.size > MAX_CLASS_IMAGE_SIZE:
        raise ValueError('La imagen debe pesar 5 MB o menos.')
    try:
        with Image.open(upload) as source:
            if source.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValueError('Usa una imagen JPG, PNG o WEBP.')
            if source.width > 6000 or source.height > 6000 or source.width * source.height > 25_000_000:
                raise ValueError('La imagen supera las dimensiones máximas permitidas.')
            source.verify()
        upload.seek(0)
        with Image.open(upload) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((1920, 1920))
            if image.mode in {'RGBA', 'LA'} or 'transparency' in image.info:
                rgba = image.convert('RGBA')
                flattened = Image.new('RGB', rgba.size, 'white')
                flattened.paste(rgba, mask=rgba.getchannel('A'))
                image = flattened
            else:
                image = image.convert('RGB')
            output = BytesIO()
            image.save(output, format='JPEG', quality=85, optimize=True)
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError('El archivo seleccionado no es una imagen válida.') from error
    return ContentFile(output.getvalue(), name=f'{uuid.uuid4().hex}.jpg')

def _store_class_image(upload):
    content = _prepare_class_image(upload)
    if content is None:
        return None
    name = default_storage.save(f'fitlife/classes/{content.name}', content)
    return default_storage.url(name)

def _delete_class_image(image_url):
    if not image_url:
        return
    media_path = urlsplit(settings.MEDIA_URL).path
    image_path = urlsplit(image_url).path
    if not image_path.startswith(media_path):
        return
    name = image_path[len(media_path):]
    if name.startswith('fitlife/classes/') and '..' not in name.split('/'):
        default_storage.delete(name)

def _json(data, status=200):
    return JsonResponse(data, status=status, encoder=DjangoJSONEncoder)

def _rows(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

def _row(sql, params=()):
    rows = _rows(sql, params)
    return rows[0] if rows else None

def _execute(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        if cursor.description is None:
            return None
        return cursor.fetchone()

def _persona(request):
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        return None
    rut = decode_token(authorization[7:].strip())
    if rut is None:
        return None
    return _row(
        'SELECT p.rut, p.nombres, p."apellidoPaterno" AS apellido_paterno, '
        'p."apellidoMaterno" AS apellido_materno, p.correo, u.activo, '
        'ARRAY(SELECT r.codigo FROM usuario_rol ur JOIN rol r USING (rol_id) '
        'WHERE ur.rut = p.rut ORDER BY r.codigo) AS roles, '
        '(SELECT rs.instalacion_id FROM recepcionista_sede rs WHERE rs.rut = p.rut) '
        'AS recepcionista_instalacion_id, '
        '(SELECT i.nombre FROM recepcionista_sede rs '
        'JOIN instalacion i USING (instalacion_id) WHERE rs.rut = p.rut) '
        'AS recepcionista_instalacion '
        'FROM persona p JOIN usuario u ON u.rut = p.rut WHERE p.rut = %s AND u.activo',
        (rut,),
    )

def _require_persona(request, roles=None):
    persona = _persona(request)
    if persona is None:
        return None, _json({'error': 'Inicia sesión para continuar.'}, 401)
    if roles and not set(persona['roles']).intersection(roles):
        return None, _json({'error': 'No tienes permisos para realizar esta acción.'}, 403)
    return persona, None

def _profile_ids(rut):
    return _row(
        'SELECT s.socio_id, i.instructor_id FROM persona p '
        'LEFT JOIN socio s ON s.rut = p.rut '
        'LEFT JOIN instructor i ON i.rut = p.rut WHERE p.rut = %s',
        (rut,),
    )

def _database_unavailable():
    return _json({
        'error': 'No fue posible completar la solicitud. Inténtalo nuevamente más tarde.'
    }, 503)

def _postgres_error_code(error):
    cause = error.__cause__
    return getattr(cause, 'sqlstate', None) or getattr(cause, 'pgcode', None)

def _postgres_constraint_name(error):
    cause = error.__cause__
    diagnostic = getattr(cause, 'diag', None)
    return getattr(diagnostic, 'constraint_name', None)
