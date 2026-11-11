import base64
import hashlib
import hmac
import json
import time
from io import BytesIO
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from django.http import JsonResponse
from django.test import SimpleTestCase
from PIL import Image

from .authentication import decode_token, issue_token
from .google_maps import resolve_google_maps_url
from .locations import REGION_CITIES
from .management.commands.bootstrap_admin import Command as BootstrapAdminCommand
from .person_names import normalize_person_name
from .passwords import validate_account_password
from .phone import normalize_chilean_phone
from .rut import normalize_rut
from .views import MAX_CLASS_IMAGE_SIZE, _execute, _prepare_class_image
from .views.admin_data import ENTITIES, _entity_fields, _validate_entity_values
from .views.common import _postgres_constraint_name
from .views.sessions import _class_assignment_exists


class ClassImageTests(SimpleTestCase):
    def test_valid_png_is_normalized_to_jpeg(self):
        image_buffer = BytesIO()
        Image.new('RGBA', (20, 10), (255, 0, 0, 128)).save(image_buffer, format='PNG')
        upload = SimpleUploadedFile('clase.png', image_buffer.getvalue(), content_type='image/png')

        prepared = _prepare_class_image(upload)

        with Image.open(prepared) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.size, (20, 10))
        self.assertTrue(prepared.name.endswith('.jpg'))

    def test_non_image_upload_is_rejected(self):
        upload = SimpleUploadedFile('clase.png', b'not an image', content_type='image/png')
        with self.assertRaisesMessage(ValueError, 'El archivo seleccionado no es una imagen válida.'):
            _prepare_class_image(upload)

    def test_oversized_upload_is_rejected(self):
        upload = SimpleNamespace(size=MAX_CLASS_IMAGE_SIZE + 1)
        with self.assertRaisesMessage(ValueError, 'La imagen debe pesar 5 MB o menos.'):
            _prepare_class_image(upload)


class FriendlyNotFoundTests(SimpleTestCase):
    def test_unknown_url_renders_custom_page_and_keeps_not_found_status(self):
        response = self.client.get('/lmffomomf')

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Perdiste el ritmo.', status_code=404)
        self.assertContains(response, 'La ruta que intentas alcanzar no existe en nuestro sistema.', status_code=404)
        self.assertContains(response, 'href="/#actividades">Explorar clases</a>', status_code=404)
        self.assertContains(response, 'href="/">Volver al inicio', status_code=404)
        self.assertContains(response, 'class="public-header"', status_code=404)
        self.assertContains(response, 'id="public-menu-toggle"', status_code=404)
        self.assertContains(response, 'id="public-sidebar"', status_code=404)
        self.assertContains(response, 'src="/static/js/not-found.js"', status_code=404)
        self.assertNotContains(response, 'Page not found', status_code=404)

    def test_api_not_found_response_remains_json(self):
        response = self.client.get('/api/not-a-real-endpoint')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response['Content-Type'], 'application/json')


class GoogleMapsLinkTests(SimpleTestCase):
    def test_extracts_coordinates_from_google_maps_pin_link(self):
        coordinates = resolve_google_maps_url(
            'https://www.google.com/maps/place/Fit+Centro/@-33.439035,-70.654187,17z'
        )
        self.assertEqual(coordinates, (Decimal('-33.439035'), Decimal('-70.654187')))

    def test_extracts_coordinates_from_google_maps_query_link(self):
        coordinates = resolve_google_maps_url(
            'https://maps.google.com/?q=-33.439035%2C-70.654187'
        )
        self.assertEqual(coordinates, (Decimal('-33.439035'), Decimal('-70.654187')))

    def test_rejects_non_google_maps_domains_without_network_access(self):
        with patch('api.google_maps.build_opener') as build_opener:
            with self.assertRaisesMessage(ValueError, 'Google Maps'):
                resolve_google_maps_url('https://maps.google.com.attacker.example/?q=1,2')
        build_opener.assert_not_called()

    def test_resolves_google_short_link_to_coordinates(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.geturl.return_value = (
            'https://www.google.com/maps/place/Fit/@-33.439035,-70.654187,17z'
        )
        with patch('api.google_maps.build_opener', return_value=opener):
            coordinates = resolve_google_maps_url('https://maps.app.goo.gl/example')
        self.assertEqual(coordinates, (Decimal('-33.439035'), Decimal('-70.654187')))
        opener.open.assert_called_once()


class RutValidationTests(SimpleTestCase):
    def test_normalizes_plain_and_formatted_ruts(self):
        self.assertEqual(normalize_rut('123456785'), '123456785')
        self.assertEqual(normalize_rut('12.345.678-5'), '123456785')

    def test_normalizes_lowercase_k_to_uppercase(self):
        self.assertEqual(normalize_rut('11111114'), '11111114')
        self.assertEqual(normalize_rut(' 1.111.111-4 '), '11111114')
        self.assertEqual(normalize_rut('1.000.005-k'), '1000005K')

    def test_rejects_invalid_verification_digit(self):
        with self.assertRaisesMessage(ValueError, 'dígito verificador'):
            normalize_rut('12.345.678-4')

    def test_rejects_invalid_characters_and_oversized_numbers(self):
        for value in ('12.345.67A-5', '1234567895', '123-'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_rut(value)


class ChileanPhoneTests(SimpleTestCase):
    def test_normalizes_national_and_international_phone_formats(self):
        self.assertEqual(normalize_chilean_phone('912345678'), '+56912345678')
        self.assertEqual(normalize_chilean_phone('+56 9 1234 5678'), '+56912345678')
        self.assertEqual(normalize_chilean_phone(''), None)

    def test_rejects_phone_numbers_with_other_than_nine_digits(self):
        for value in ('12345678', '9123456780', '91234abcd'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_chilean_phone(value)

    def test_extracts_unique_phone_constraint_name_from_postgres_error(self):
        error = Exception('duplicate phone')
        cause = Exception('postgres duplicate')
        cause.diag = SimpleNamespace(constraint_name='uq_persona_telefono')
        error.__cause__ = cause
        self.assertEqual(_postgres_constraint_name(error), 'uq_persona_telefono')


class PersonNameValidationTests(SimpleTestCase):
    def test_accepts_spanish_letters_and_normalizes_whitespace(self):
        self.assertEqual(normalize_person_name('  María   José '), 'María José')
        self.assertEqual(normalize_person_name('Muñoz'), 'Muñoz')

    def test_rejects_numbers_special_characters_and_names_under_three_letters(self):
        for value in ('9', '+4494', 'Jo', 'Ana- María', 'José_'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_person_name(value)

    def test_optional_maternal_surname_can_be_empty(self):
        self.assertIsNone(normalize_person_name('', 'apellido materno', required=False))


class PasswordPolicyTests(SimpleTestCase):
    def test_accepts_long_non_common_passwords(self):
        validate_account_password('Nube-verde-7!Reloj')

    def test_rejects_short_common_and_oversized_passwords(self):
        for password in ('short', 'password123456', 'A' * 257):
            with self.subTest(password=password[:16]), self.assertRaises(ValueError):
                validate_account_password(password)

    def test_rejects_password_similar_to_account_attributes(self):
        user = get_user_model()(
            username='1000005K',
            email='ana@example.test',
            first_name='Ana',
            last_name='Rojas',
        )
        with self.assertRaises(ValueError):
            validate_account_password('ana@example.test', user)


class RoomApiTests(SimpleTestCase):
    def test_room_creation_requires_a_positive_capacity(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)):
            response = self.client.post(
                '/api/rooms',
                data=json.dumps({'nombre': 'Sala Norte', 'instalacion_id': 2, 'capacidad': 0}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('capacidad', response.json()['error'])

    def test_room_creation_saves_the_selected_installation(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._row', return_value={'instalacion_id': 2}), \
                patch('api.views.resources._execute', return_value=(19,)) as execute:
            response = self.client.post(
                '/api/rooms',
                data=json.dumps({'nombre': 'Sala Norte', 'instalacion_id': 2, 'capacidad': 24}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['sala_id'], 19)
        self.assertEqual(execute.call_args.args[1], (2, 'Sala Norte', 24))

    def test_machine_creation_requires_an_active_installation(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._row', return_value=None), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/machines',
                data=json.dumps({
                    'nombre': 'Cinta 1',
                    'categoria': 'Cardio',
                    'instalacion_id': 2,
                    'sala_id': 12,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()

    def test_machine_creation_requires_a_room_from_the_selected_installation(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._row', side_effect=[
                    {'instalacion_id': 2},
                    None,
                ]), patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/machines',
                data=json.dumps({
                    'nombre': 'Cinta 1',
                    'categoria': 'Cardio',
                    'instalacion_id': 2,
                    'sala_id': 12,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('sala activa', response.json()['error'])
        execute.assert_not_called()

    def test_machine_creation_persists_its_room_and_installation(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._row', side_effect=[
                    {'instalacion_id': 2},
                    {'sala_id': 12},
                ]), patch('api.views.resources._execute', return_value=(31,)) as execute:
            response = self.client.post(
                '/api/machines',
                data=json.dumps({
                    'nombre': 'Cinta 1',
                    'categoria': 'Cardio',
                    'instalacion_id': 2,
                    'sala_id': 12,
                    'observacion': 'Mantención preventiva',
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['maquina_id'], 31)
        self.assertEqual(execute.call_args.args[1], (
            'Cinta 1', 'Cardio', 2, 12, 'Mantención preventiva',
        ))

    def test_machine_room_assignment_is_limited_to_its_installation(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._row', side_effect=[
                    {'instalacion_id': 2},
                    None,
                ]), patch('api.views.resources._execute') as execute:
            response = self.client.patch(
                '/api/machines/31',
                data=json.dumps({'sala_id': 14}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('sala activa', response.json()['error'])
        execute.assert_not_called()

    def test_installation_professionals_add_only_new_valid_active_ids(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._row', return_value={'instalacion_id': 2}), \
                patch('api.views.resources._rows', side_effect=[
                    [{'instructor_id': 5}],
                    [],
                ]), \
                patch('api.views.resources._execute') as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.put(
                '/api/installations/2/instructors',
                data=json.dumps({'instructor_ids': [5]}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(
            'INSERT INTO instalacion_instructor' in call.args[0]
            and call.args[1] == (2, 5)
            for call in execute.call_args_list
        ))

    def test_installation_professional_cannot_be_removed_from_an_active_class(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._row', return_value={'instalacion_id': 2}), \
                patch('api.views.resources._rows', side_effect=[
                    [{'instructor_id': 5}],
                    [{'sesion_id': 8}],
                ]), \
                patch('api.views.resources._execute') as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.put(
                '/api/installations/2/instructors',
                data=json.dumps({'instructor_ids': []}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 409)
        self.assertIn('clases activas o futuras', response.json()['error'])
        execute.assert_not_called()

    def test_installation_creation_saves_required_branch_details(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute', return_value=(12,)) as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'direccion': 'Compañía de Jesús 1214',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'aforo_maximo': 200,
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'latitud': -33.439035,
                    'longitud': -70.654187,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['instalacion_id'], 12)
        self.assertEqual(
            execute.call_args_list[0].args[1],
            ('FitLife Centro', 'Compañía de Jesús 1214', 'Metropolitana de Santiago', 'Santiago',
             200, False, 0, False, 0,
             False, 0, False, 0,
             '6h - 22h', '8h - 16h', '', Decimal('-33.439035'), Decimal('-70.654187'), None),
        )

    def test_installation_creation_saves_dressing_room_and_shower_capacities(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute', return_value=(12,)) as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'direccion': 'Av. Central 123',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'aforo_maximo': 200,
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'latitud': -33.439035,
                    'longitud': -70.654187,
                    'tiene_vestidores': True,
                    'cantidad_vestidores': 12,
                    'tiene_duchas': True,
                    'cantidad_duchas': 18,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        params = execute.call_args_list[0].args[1]
        self.assertEqual(params[9:13], (True, 12, True, 18))

    def test_installation_requires_positive_dressing_room_and_shower_capacities(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        for service, quantity, message in (
            ('tiene_vestidores', 'cantidad_vestidores', 'vestidores'),
            ('tiene_duchas', 'cantidad_duchas', 'duchas'),
        ):
            with self.subTest(service=service), \
                    patch('api.views.resources._require_persona', return_value=(admin, None)), \
                    patch('api.views.resources._execute') as execute:
                response = self.client.post(
                    '/api/installations',
                    data=json.dumps({
                        'nombre': 'FitLife Centro',
                        'direccion': 'Av. Central 123',
                        'region': 'Metropolitana de Santiago',
                        'ciudad': 'Santiago',
                        'aforo_maximo': 200,
                        'horario_lunes_viernes': '6h - 22h',
                        'horario_sabados_dom_festivos': '8h - 16h',
                        'latitud': -33.439035,
                        'longitud': -70.654187,
                        service: True,
                        quantity: 0,
                    }),
                    content_type='application/json',
                )
            self.assertEqual(response.status_code, 400)
            self.assertIn(message, response.json()['error'])
            execute.assert_not_called()

    def test_installation_creation_saves_parking_capacity(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute', return_value=(12,)) as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'aforo_maximo': 200,
                    'tiene_estacionamiento': True,
                    'cupos_estacionamiento': 35,
                    'direccion': 'Av. Central 123',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'latitud': -33.439035,
                    'longitud': -70.654187,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            execute.call_args_list[0].args[1],
            ('FitLife Centro', 'Av. Central 123', 'Metropolitana de Santiago', 'Santiago',
             200, False, 0, True, 35,
             False, 0, False, 0,
             '6h - 22h', '8h - 16h', '', Decimal('-33.439035'), Decimal('-70.654187'), None),
        )

    def test_installation_creation_saves_hours_and_map_coordinates(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute', return_value=(12,)) as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'aforo_maximo': 200,
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'direccion': 'Av. Central 123',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'latitud': -33.439035,
                    'longitud': -70.654187,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            execute.call_args_list[0].args[1][13:18],
            ('6h - 22h', '8h - 16h', '', Decimal('-33.439035'), Decimal('-70.654187')),
        )

    def test_installation_creation_resolves_google_maps_link(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources.resolve_google_maps_url', return_value=(
                    Decimal('-33.439035'), Decimal('-70.654187'),
                )) as resolve_link, \
                patch('api.views.resources._execute', return_value=(12,)) as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'aforo_maximo': 200,
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'direccion': 'Av. Central 123',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'mapa_url': 'https://maps.app.goo.gl/example',
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        resolve_link.assert_called_once_with('https://maps.app.goo.gl/example')
        self.assertEqual(
            execute.call_args_list[0].args[1][16:18],
            (Decimal('-33.439035'), Decimal('-70.654187')),
        )

    def test_installation_creation_links_selected_active_plans(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._rows', return_value=[{'plan_id': 3}]), \
                patch('api.views.resources._execute', side_effect=[(12,), None, None]) as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'aforo_maximo': 200,
                    'direccion': 'Av. Central 123',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'latitud': -33.439035,
                    'longitud': -70.654187,
                    'planes_ids': [3],
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 201)
        self.assertIn(
            ('INSERT INTO instalacion_plan (instalacion_id, plan_id) VALUES (%s, %s)', (12, 3)),
            [call.args for call in execute.call_args_list],
        )

    def test_installation_requires_both_valid_map_coordinates(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'aforo_maximo': 200,
                    'direccion': 'Av. Central 123',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'latitud': -33.439035,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('latitud y la longitud', response.json()['error'])
        execute.assert_not_called()

    def test_installation_requires_admin_to_provide_address_and_opening_hours(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/installations',
                data=json.dumps({'nombre': 'FitLife Centro', 'aforo_maximo': 200}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('dirección', response.json()['error'])
        execute.assert_not_called()

    def test_installation_detail_updates_hours_and_location(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute', return_value=(12,)) as execute, \
                patch('api.views.resources.transaction.atomic', return_value=nullcontext()):
            response = self.client.patch(
                '/api/installations/12',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'direccion': 'Compañía de Jesús 1214, local 218',
                    'aforo_maximo': 200,
                    'tiene_lockers': False,
                    'cantidad_lockers': 0,
                    'tiene_estacionamiento': False,
                    'cupos_estacionamiento': 0,
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'caracteristicas': 'Vestidores y duchas',
                    'region': 'Metropolitana de Santiago',
                    'ciudad': 'Santiago',
                    'latitud': -33.439035,
                    'longitud': -70.654187,
                    'planes_ids': [],
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(execute.call_args_list[0].args[1][-1], 12)

    def test_installation_requires_a_positive_parking_capacity_when_enabled(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'aforo_maximo': 200,
                    'tiene_estacionamiento': True,
                    'cupos_estacionamiento': 0,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()

    def test_installation_requires_a_positive_locker_count_when_enabled(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'aforo_maximo': 200,
                    'tiene_lockers': True,
                    'cantidad_lockers': 0,
                }),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()


class AccessPointApiTests(SimpleTestCase):
    admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}

    def test_access_point_creation_persists_site_and_direction(self):
        with patch('api.views.resources._require_persona', return_value=(self.admin, None)), \
                patch('api.views.resources._row', return_value={
                    'instalacion_id': 2, 'tiene_estacionamiento': True,
                }), \
                patch('api.views.resources._execute', return_value=(19,)) as execute:
            response = self.client.post(
                '/api/access-points',
                data=json.dumps({
                    'instalacion_id': 2,
                    'nombre': 'Entrada principal',
                    'tipo': 'ENTRADA',
                    'uso': 'ESTACIONAMIENTO',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['punto_acceso_id'], 19)
        self.assertIn('punto_acceso', execute.call_args.args[0])
        self.assertEqual(execute.call_args.args[1], (2, 'Entrada principal', 'ENTRADA', 'ESTACIONAMIENTO'))

    def test_access_point_creation_rejects_invalid_direction_or_inactive_site(self):
        for body, expected_message in (
            ({'instalacion_id': 2, 'nombre': 'Entrada', 'tipo': 'CAMBIO'}, 'tipo válido'),
            ({'instalacion_id': 2, 'nombre': 'Entrada', 'tipo': 'ENTRADA'}, 'sede activa'),
            ({'instalacion_id': 2.5, 'nombre': 'Entrada', 'tipo': 'ENTRADA'}, 'sede válida'),
        ):
            with self.subTest(body=body), \
                    patch('api.views.resources._require_persona', return_value=(self.admin, None)), \
                    patch('api.views.resources._row', return_value=None), \
                    patch('api.views.resources._execute') as execute:
                response = self.client.post(
                    '/api/access-points',
                    data=json.dumps(body),
                    content_type='application/json',
                )
            self.assertEqual(response.status_code, 400)
            self.assertIn(expected_message, response.json()['error'])
            execute.assert_not_called()

    def test_access_point_creation_rejects_parking_usage_without_site_parking(self):
        with patch('api.views.resources._require_persona', return_value=(self.admin, None)), \
                patch('api.views.resources._row', return_value={
                    'instalacion_id': 2, 'tiene_estacionamiento': False,
                }), patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/access-points',
                data=json.dumps({
                    'instalacion_id': 2,
                    'nombre': 'Acceso estacionamiento',
                    'tipo': 'BIDIRECCIONAL',
                    'uso': 'ESTACIONAMIENTO',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('cuente con estacionamiento', response.json()['error'])
        execute.assert_not_called()

    def test_access_point_active_status_can_be_changed(self):
        with patch('api.views.resources._require_persona', return_value=(self.admin, None)), \
                patch('api.views.resources._execute', return_value=(19,)) as execute:
            response = self.client.patch(
                '/api/access-points/19',
                data=json.dumps({'activo': False}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(execute.call_args.args[1], (False, 19))


class DashboardApiTests(SimpleTestCase):
    def test_receptionist_dashboard_scopes_access_data_to_assigned_site(self):
        receptionist = {
            'rut': '123456785',
            'roles': ['RECEPCIONISTA'],
            'recepcionista_instalacion_id': 7,
        }
        with patch('api.views.dashboard._require_persona', return_value=(receptionist, None)), \
                patch('api.views.dashboard._profile_ids', return_value={
                    'socio_id': None, 'instructor_id': None,
                }), patch('api.views.dashboard._row', return_value=None), \
                patch('api.views.dashboard._rows', return_value=[]) as rows:
            response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 200)
        scoped_queries = [
            call for call in rows.call_args_list
            if 'SELECT * FROM vw_aforo_actual' in call.args[0]
            or 'SELECT v.* FROM vw_accesos_recientes' in call.args[0]
            or 'FROM punto_acceso pa' in call.args[0]
        ]
        self.assertEqual(len(scoped_queries), 3)
        for call in scoped_queries:
            self.assertIn('%s', call.args[0])
            self.assertEqual(call.args[1], (7,))

    def test_dashboard_exposes_active_gym_details_to_members(self):
        member = {'rut': '123456785', 'roles': ['SOCIO']}
        installation = {
            'instalacion_id': 1,
            'nombre': 'Fit Centro',
            'direccion': None,
            'horario_lunes_viernes': None,
            'horario_sabados_dom_festivos': None,
            'latitud': None,
            'longitud': None,
            'areas': [],
            'plan_ids': [],
            'planes': [],
        }

        def dashboard_rows(query, params=()):
            if 'FROM instalacion i WHERE i.activa ORDER BY i.nombre' in query:
                return [installation]
            return []

        with patch('api.views.dashboard._require_persona', return_value=(member, None)), \
                patch('api.views.dashboard._profile_ids', return_value={'socio_id': 3, 'instructor_id': None}), \
                patch('api.views.dashboard._row', return_value=None), \
                patch('api.views.dashboard._rows', side_effect=dashboard_rows) as rows:
            response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['gym_locations'][0]['nombre'], 'Fit Centro')
        installations_query = next(
            call.args[0] for call in rows.call_args_list
            if 'FROM instalacion i WHERE i.activa ORDER BY i.nombre' in call.args[0]
        )
        self.assertIn('horario_lunes_viernes', installations_query)
        self.assertIn('latitud, longitud', installations_query)
        self.assertIn('AS areas', installations_query)
        self.assertNotIn('i.direccion IS NOT NULL', installations_query)
        self.assertNotIn('i.latitud IS NOT NULL', installations_query)
        self.assertTrue(any(
            'JOIN sala sa USING (sala_id) JOIN instalacion i USING (instalacion_id)' in call.args[0]
            and 'LIMIT 500' in call.args[0]
            for call in rows.call_args_list
        ))

    def test_public_installations_endpoint_returns_sites_and_plan_prices(self):
        installation = {'instalacion_id': 4, 'nombre': 'Fit Centro', 'areas': []}
        with patch('api.views.resources._rows', side_effect=[
                [installation],
                [{'plan_id': 2, 'nombre': 'Smart', 'precio_referencia': Decimal('36900')}],
                [],
        ]) as rows:
            response = self.client.get('/api/public/installations')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['installations'][0]['plans'][0]['nombre'], 'Smart')
        self.assertEqual(response.json()['sessions'], [])
        self.assertEqual(rows.call_count, 3)

    def test_admin_dashboard_includes_past_and_finalized_classes(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.dashboard._require_persona', return_value=(admin, None)), \
                patch('api.views.dashboard._profile_ids', return_value={'socio_id': None, 'instructor_id': None}), \
                patch('api.views.dashboard._row', return_value=None), \
                patch('api.views.dashboard._rows', return_value=[]) as rows:
            response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['admin_sessions'], [])
        admin_session_query = next(
            call.args[0] for call in rows.call_args_list
            if 'FROM sesion_clase sc JOIN actividad a USING (actividad_id)' in call.args[0]
            and 'ORDER BY sc.inicio DESC LIMIT 100' in call.args[0]
        )
        self.assertNotIn("sc.estado = 'PROGRAMADA'", admin_session_query)
        self.assertNotIn('sc.inicio > CURRENT_TIMESTAMP', admin_session_query)

    def test_admin_dashboard_loads_points_for_site_management(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        point = {
            'punto_acceso_id': 19,
            'instalacion_id': 2,
            'instalacion': 'Fit Center',
            'nombre': 'Entrada principal',
            'tipo': 'ENTRADA',
            'uso': 'GENERAL',
            'activo': True,
            'tiene_estacionamiento': False,
        }
        with patch('api.views.dashboard._require_persona', return_value=(admin, None)), \
                patch('api.views.dashboard._profile_ids', return_value={
                    'socio_id': None, 'instructor_id': None,
                }), patch('api.views.dashboard._row', return_value=None), \
                patch('api.views.dashboard._rows', side_effect=lambda query, params=():
                      [point] if 'FROM punto_acceso pa' in query else []) as rows:
            response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['admin_access_points'], [point])
        queries = [
            call.args[0] for call in rows.call_args_list
            if 'FROM punto_acceso pa' in call.args[0]
        ]
        self.assertEqual(len(queries), 2)
        admin_points_query = next(query for query in queries if 'pa.tipo, pa.uso, pa.activo' in query)
        validation_points_query = next(query for query in queries if 'pa.punto_acceso_id, pa.nombre, pa.uso' in query)
        self.assertIn('pa.uso', admin_points_query)
        self.assertIn("pa.uso <> 'ESTACIONAMIENTO' OR i.tiene_estacionamiento", validation_points_query)


class MembershipApiTests(SimpleTestCase):
    admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
    member = {'rut': '123456785', 'roles': ['SOCIO']}

    def test_customer_can_start_membership_payment_with_webpay(self):
        transbank = MagicMock()
        transbank.create.return_value = {
            'token': 'webpay-token',
            'url': 'https://webpay3gint.transbank.cl/webpayserver/initTransaction',
        }
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._row', side_effect=[
                    {'socio_id': 3},
                    {'plan_id': 5, 'duracion_dias': 30, 'precio_referencia': Decimal('10000')},
                    None,
                ]) as row, \
                patch('api.views.memberships._execute', side_effect=[(29,), (41,), (41,)]) as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()), \
                patch('api.views.memberships.webpay_transaction', return_value=transbank):
            response = self.client.post(
                '/api/memberships/purchase',
                data=json.dumps({'plan_id': 5, 'instalacion_id': 12, 'metodo_pago': 'WEBPAY'}),
                content_type='application/json',
                HTTP_HOST='localhost',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['token'], 'webpay-token')
        self.assertIn('webpay3gint.transbank.cl', response.json()['url'])
        self.assertEqual(execute.call_count, 3)
        self.assertIn('PENDIENTE', execute.call_args_list[0].args[0])
        self.assertIn('instalacion_id', execute.call_args_list[0].args[0])
        self.assertEqual(execute.call_args_list[0].args[1][2], 12)
        self.assertIn("'WEBPAY'::metodo_pago", execute.call_args_list[1].args[0])
        self.assertEqual(execute.call_args_list[1].args[1][1], Decimal('10000'))
        self.assertIn('referencia_externa', execute.call_args_list[2].args[0])
        self.assertEqual(transbank.create.call_args.args[0], 'FL00000000000000000041')
        self.assertIn('/api/payments/webpay/return', transbank.create.call_args.args[3])
        self.assertIn('m.fecha_fin >= CURRENT_DATE', row.call_args_list[2].args[0])

    def test_customer_purchase_rejects_cash_before_creating_records(self):
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._execute') as execute:
            response = self.client.post(
                '/api/memberships/purchase',
                data=json.dumps({'plan_id': 5, 'metodo_pago': 'EFECTIVO'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn('No se acepta efectivo', response.json()['error'])
        execute.assert_not_called()

    def test_customer_purchase_rejects_non_integer_plan_ids(self):
        for plan_id in (True, 5.2, '5.2'):
            with self.subTest(plan_id=plan_id), \
                    patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                    patch('api.views.memberships._row') as row:
                response = self.client.post(
                    '/api/memberships/purchase',
                    data=json.dumps({'plan_id': plan_id, 'instalacion_id': 12, 'metodo_pago': 'WEBPAY'}),
                    content_type='application/json',
                )
            self.assertEqual(response.status_code, 400)
            row.assert_not_called()

    def test_customer_purchase_requires_a_member_account(self):
        error = JsonResponse({'error': 'No tienes permisos.'}, status=403)
        with patch('api.views.memberships._require_persona', return_value=(None, error)), \
                patch('api.views.memberships._execute') as execute:
            response = self.client.post(
                '/api/memberships/purchase',
                data=json.dumps({'plan_id': 5, 'instalacion_id': 12, 'metodo_pago': 'WEBPAY'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 403)
        execute.assert_not_called()

    def test_free_customer_plan_activates_without_payment(self):
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._row', side_effect=[
                    {'socio_id': 3},
                    {'plan_id': 5, 'duracion_dias': 30, 'precio_referencia': Decimal('0')},
                    None,
                ]), patch('api.views.memberships._execute', return_value=(29,)) as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()), \
                patch('api.views.memberships.webpay_transaction') as webpay:
            response = self.client.post(
                '/api/memberships/purchase',
                data=json.dumps({'plan_id': 5, 'instalacion_id': 12, 'metodo_pago': 'WEBPAY'}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()['gratis'])
        self.assertIn("'ACTIVA'", execute.call_args.args[0])
        webpay.assert_not_called()

    def test_webpay_return_activates_membership_only_after_verified_approval(self):
        transbank = MagicMock()
        transbank.commit.return_value = {
            'buy_order': 'FL00000000000000000041',
            'status': 'AUTHORIZED',
            'response_code': 0,
            'amount': 10000,
        }
        payment = {
            'pago_id': 41,
            'membresia_id': 29,
            'monto': Decimal('10000'),
            'estado': 'PENDIENTE',
            'precio_acordado': Decimal('10000'),
            'membresia_estado': 'PENDIENTE',
        }
        with patch('api.views.memberships.webpay_transaction', return_value=transbank), \
                patch('api.views.memberships._row', return_value=payment), \
                patch('api.views.memberships._execute') as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/payments/webpay/return',
                data={'token_ws': 'provider-token'},
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/panel/?pago=aprobado')
        transbank.commit.assert_called_once_with('provider-token')
        self.assertIn("'APROBADO'", execute.call_args_list[0].args[0])
        self.assertIn("'ACTIVA'", execute.call_args_list[1].args[0])

    def test_webpay_return_does_not_activate_or_reject_a_charged_amount_mismatch(self):
        transbank = MagicMock()
        transbank.commit.return_value = {
            'buy_order': 'FL00000000000000000041',
            'status': 'AUTHORIZED',
            'response_code': 0,
            'amount': 9999,
        }
        payment = {
            'pago_id': 41,
            'membresia_id': 29,
            'monto': Decimal('10000'),
            'estado': 'PENDIENTE',
            'precio_acordado': Decimal('10000'),
            'membresia_estado': 'PENDIENTE',
        }
        with patch('api.views.memberships.webpay_transaction', return_value=transbank), \
                patch('api.views.memberships._row', return_value=payment), \
                patch('api.views.memberships._execute') as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/payments/webpay/return',
                data={'token_ws': 'provider-token'},
            )

        self.assertEqual(response['Location'], '/panel/?pago=verificacion')
        execute.assert_not_called()

    def test_webpay_cancellation_marks_only_its_pending_order_cancelled(self):
        transbank = MagicMock()
        transbank.status.return_value = {
            'buy_order': 'FL00000000000000000041',
            'status': 'INITIALIZED',
        }
        with patch('api.views.memberships.webpay_transaction', return_value=transbank), \
                patch('api.views.memberships._row', return_value={'pago_id': 41, 'membresia_id': 29}), \
                patch('api.views.memberships._execute') as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/payments/webpay/return',
                data={
                    'TBK_TOKEN': 'provider-token',
                    'TBK_ORDEN_COMPRA': 'FL00000000000000000041',
                },
            )

        self.assertEqual(response['Location'], '/panel/?pago=cancelado')
        transbank.status.assert_called_once_with('provider-token')
        self.assertEqual(execute.call_count, 2)

    def test_plan_creation_persists_configured_benefits(self):
        with patch('api.views.memberships._require_persona', return_value=(self.admin, None)), \
                patch('api.views.memberships._rows', return_value=[
                    {'instalacion_id': 2}, {'instalacion_id': 4},
                ]), patch('api.views.memberships._execute', return_value=(8,)) as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/plans',
                data=json.dumps({
                    'tipo': 'PLAN',
                    'nombre': 'Fit Plus',
                    'descripcion': 'Plan completo',
                    'duracion_dias': 30,
                    'precio_referencia': 24990,
                    'incluye_entrenador_personal': True,
                    'incluye_lockers': True,
                    'incluye_estacionamiento': True,
                    'otros_beneficios': 'Evaluación nutricional\nAcceso a piscina',
                    'instalaciones_ids': [4, 2],
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        plan_insert = execute.call_args_list[0]
        self.assertIn('tipo', plan_insert.args[0])
        self.assertIn('incluye_entrenador_personal', plan_insert.args[0])
        self.assertIn('incluye_lockers', plan_insert.args[0])
        self.assertIn('incluye_estacionamiento', plan_insert.args[0])
        self.assertEqual(tuple(plan_insert.args[1][-6:]), (
            True,
            True,
            True,
            'Evaluación nutricional\nAcceso a piscina',
            False,
            False,
        ))
        self.assertEqual(
            [call.args[1] for call in execute.call_args_list[2:]],
            [(2, 8), (4, 8)],
        )

    def test_plan_creation_supports_global_memberships_without_site_associations(self):
        with patch('api.views.memberships._require_persona', return_value=(self.admin, None)), \
                patch('api.views.memberships._rows') as rows, \
                patch('api.views.memberships._execute', return_value=(8,)) as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/plans',
                data=json.dumps({
                    'tipo': 'MEMBRESIA',
                    'nombre': 'Fit Global',
                    'duracion_dias': 30,
                    'precio_referencia': 36900,
                    'acceso_todas_sedes': True,
                    'instalaciones_ids': [],
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertIn('acceso_todas_sedes', execute.call_args_list[0].args[0])
        self.assertIn(True, execute.call_args_list[0].args[1])
        rows.assert_not_called()
        self.assertFalse(any('INSERT INTO instalacion_plan' in call.args[0] for call in execute.call_args_list))

    def test_free_trial_plan_requires_one_site_and_zero_price(self):
        with patch('api.views.memberships._require_persona', return_value=(self.admin, None)), \
                patch('api.views.memberships._rows', return_value=[{'instalacion_id': 2}]), \
                patch('api.views.memberships._execute', side_effect=[(8,), None, None]) as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/plans',
                data=json.dumps({
                    'tipo': 'MEMBRESIA',
                    'nombre': 'Prueba Fit Centro',
                    'duracion_dias': 7,
                    'precio_referencia': 0,
                    'es_prueba_gratuita': True,
                    'instalaciones_ids': [2],
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertIn('es_prueba_gratuita', execute.call_args_list[0].args[0])
        self.assertIn(True, execute.call_args_list[0].args[1])
        self.assertEqual(execute.call_args_list[-1].args[1], (2, 8))

    def test_member_can_redeem_a_free_trial_without_payment(self):
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._row', side_effect=[
                    {'socio_id': 3},
                    None,
                    {'plan_id': 5, 'duracion_dias': 7, 'precio_referencia': Decimal('0')},
                    None,
                ]) as row, patch('api.views.memberships._execute', side_effect=[(31,), None]) as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/memberships/trial',
                data=json.dumps({'plan_id': 5, 'instalacion_id': 12}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['membresia_id'], 31)
        self.assertIn('CURRENT_DATE + %s - 1', execute.call_args_list[0].args[0])
        self.assertIn('INSERT INTO prueba_socio', execute.call_args_list[1].args[0])
        self.assertIn('m.fecha_fin >= CURRENT_DATE', row.call_args_list[3].args[0])
        self.assertFalse(any('INSERT INTO pago' in call.args[0] for call in execute.call_args_list))

    def test_member_cannot_redeem_a_second_free_trial(self):
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._row', side_effect=[
                    {'socio_id': 3}, {'rut': self.member['rut']},
                ]), patch('api.views.memberships._execute') as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/memberships/trial',
                data=json.dumps({'plan_id': 5, 'instalacion_id': 12}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn('Ya canjeaste', response.json()['error'])
        execute.assert_not_called()

    def test_free_trial_plans_are_not_available_through_paid_purchase(self):
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._row', side_effect=[{'socio_id': 3}, None]) as row, \
                patch('api.views.memberships._execute') as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/memberships/purchase',
                data=json.dumps({
                    'plan_id': 5,
                    'instalacion_id': 12,
                    'metodo_pago': 'WEBPAY',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn('NOT pm.es_prueba_gratuita', row.call_args_list[1].args[0])
        execute.assert_not_called()

    def test_public_plans_include_their_active_site_names(self):
        with patch('api.views.memberships._rows', return_value=[
            {'plan_id': 3, 'nombre': 'Plata', 'sedes': ['Fit Centro', 'Fit Norte']},
        ]) as rows:
            response = self.client.get('/api/plans')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['plans'][0]['sedes'], ['Fit Centro', 'Fit Norte'])
        self.assertIn('AS sedes', rows.call_args.args[0])
        self.assertIn('i.activa', rows.call_args.args[0])

    def test_plan_creation_requires_at_least_one_site(self):
        with patch('api.views.memberships._require_persona', return_value=(self.admin, None)), \
                patch('api.views.memberships._execute') as execute:
            response = self.client.post(
                '/api/plans',
                data=json.dumps({
                    'tipo': 'PLAN',
                    'nombre': 'Fit Plus',
                    'duracion_dias': 30,
                    'precio_referencia': 24990,
                    'instalaciones_ids': [],
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('al menos una sede', response.json()['error'])
        execute.assert_not_called()

    def test_plan_creation_rejects_non_integer_durations(self):
        for duration in (True, 7.5, '7.5'):
            with self.subTest(duration=duration), \
                    patch('api.views.memberships._require_persona', return_value=(self.admin, None)), \
                    patch('api.views.memberships._execute') as execute:
                response = self.client.post(
                    '/api/plans',
                    data=json.dumps({
                        'tipo': 'PLAN',
                        'nombre': 'Fit Plus',
                        'duracion_dias': duration,
                        'precio_referencia': 24990,
                        'instalaciones_ids': [2],
                    }),
                    content_type='application/json',
                )

            self.assertEqual(response.status_code, 400)
            self.assertIn('duración válida', response.json()['error'])
            execute.assert_not_called()

    def test_plan_creation_rejects_inactive_or_unknown_site_ids(self):
        with patch('api.views.memberships._require_persona', return_value=(self.admin, None)), \
                patch('api.views.memberships._rows', return_value=[]), \
                patch('api.views.memberships._execute') as execute:
            response = self.client.post(
                '/api/plans',
                data=json.dumps({
                    'tipo': 'PLAN',
                    'nombre': 'Fit Plus',
                    'duracion_dias': 30,
                    'precio_referencia': 24990,
                    'instalaciones_ids': [999],
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('no están disponibles', response.json()['error'])
        execute.assert_not_called()

    def test_plan_creation_rejects_types_outside_the_two_supported_options(self):
        with patch('api.views.memberships._require_persona', return_value=(self.admin, None)), \
                patch('api.views.memberships._execute') as execute:
            response = self.client.post(
                '/api/plans',
                data=json.dumps({
                    'tipo': 'SUSCRIPCION',
                    'nombre': 'Fit Plus',
                    'duracion_dias': 30,
                    'precio_referencia': 24990,
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('tipo Plan o Membresía', response.json()['error'])
        execute.assert_not_called()

    def test_installation_rejects_unknown_region_before_writing(self):
        admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.resources._require_persona', return_value=(admin, None)), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/installations',
                data=json.dumps({
                    'nombre': 'FitLife Centro',
                    'direccion': 'Av. Central 123',
                    'region': 'Región inexistente',
                    'ciudad': 'Santiago',
                    'aforo_maximo': 200,
                    'horario_lunes_viernes': '6h - 22h',
                    'horario_sabados_dom_festivos': '8h - 16h',
                    'mapa_url': 'https://maps.google.com/?q=-33.439035,-70.654187',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('región y una ciudad', response.json()['error'])
        execute.assert_not_called()

    def test_manual_membership_creation_is_disabled(self):
        for role in (self.admin, self.member, {'rut': '11111114', 'roles': ['RECEPCIONISTA']}):
            with self.subTest(role=role), \
                    patch('api.views.memberships._execute') as execute:
                response = self.client.post(
                    '/api/memberships',
                    data=json.dumps({'socio_id': 3, 'plan_id': 5, 'instalacion_id': 12}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 405)
                self.assertIn('asignación manual', response.json()['error'])
                execute.assert_not_called()

    def test_customer_purchase_requires_a_site(self):
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._row') as row:
            response = self.client.post(
                '/api/memberships/purchase',
                data=json.dumps({'plan_id': 5, 'metodo_pago': 'WEBPAY'}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('sede válida', response.json()['error'])
        row.assert_not_called()

    def test_customer_purchase_rejects_plan_not_offered_at_site(self):
        with patch('api.views.memberships._require_persona', return_value=(self.member, None)), \
                patch('api.views.memberships._row', side_effect=[{'socio_id': 3}, None]), \
                patch('api.views.memberships._execute') as execute, \
                patch('api.views.memberships.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/memberships/purchase',
                data=json.dumps({
                    'plan_id': 5,
                    'instalacion_id': 12,
                    'metodo_pago': 'WEBPAY',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 404)
        self.assertIn('sede seleccionada', response.json()['error'])
        execute.assert_not_called()


class UserRoleApiTests(SimpleTestCase):
    admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}

    def test_admin_can_assign_member_and_instructor_roles_with_professional_profile(self):
        with patch('api.views.staff._require_persona', return_value=(self.admin, None)), \
                patch('api.views.staff._row', side_effect=[
                    {'rut': '123456785', 'activo': True},
                    {'instructor_id': 21},
                ]), patch('api.views.staff._rows', side_effect=[
                    [],
                    [{'rol_id': 1, 'codigo': 'SOCIO'}, {'rol_id': 2, 'codigo': 'INSTRUCTOR'}],
                ]), patch('api.views.staff._execute') as execute, \
                patch('api.views.staff.transaction.atomic', return_value=nullcontext()):
            response = self.client.patch(
                '/api/users/123456785/roles',
                data=json.dumps({
                    'roles': ['socio', 'instructor'],
                    'tipo_profesional': 'COACH',
                    'especialidad': 'Fuerza',
                    'instalacion_id': None,
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        statements = [item.args[0] for item in execute.call_args_list]
        self.assertIn('DELETE FROM usuario_rol', statements[0])
        self.assertTrue(any('INSERT INTO socio' in statement for statement in statements))
        self.assertTrue(any('INSERT INTO perfil_instructor' in statement for statement in statements))

    def test_admin_cannot_remove_the_last_active_administrator(self):
        with patch('api.views.staff._require_persona', return_value=(self.admin, None)), \
                patch('api.views.staff._row', side_effect=[
                    {'rut': self.admin['rut'], 'activo': True},
                    {'cantidad': 1},
                ]), patch('api.views.staff._execute') as execute, \
                patch('api.views.staff._rows', return_value=[
                    {'codigo': 'ADMINISTRADOR'},
                ]) as rows, \
                patch('api.views.staff.transaction.atomic', return_value=nullcontext()):
            response = self.client.patch(
                f"/api/users/{self.admin['rut']}/roles",
                data=json.dumps({
                    'roles': ['SOCIO'],
                    'tipo_profesional': '',
                    'especialidad': '',
                    'instalacion_id': None,
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn('al menos una cuenta administradora', response.json()['error'])
        rows.assert_called_once()
        self.assertIn('FROM usuario_rol', rows.call_args.args[0])
        execute.assert_not_called()


class CredentialApiTests(SimpleTestCase):
    member = {'rut': '123456785', 'roles': ['SOCIO']}

    def test_instructor_dashboard_includes_recorded_attendance(self):
        instructor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}
        with patch('api.views.dashboard._require_persona', return_value=(instructor, None)), \
                patch('api.views.dashboard._profile_ids', return_value={
                    'socio_id': None, 'instructor_id': 21,
                }), \
                patch('api.views.dashboard._row', return_value={'tipo': 'MONITOR'}), \
                patch('api.views.dashboard._rows', return_value=[]) as rows:
            response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 200)
        attendee_query = next(
            call.args[0] for call in rows.call_args_list
            if 'FROM reserva r JOIN sesion_clase sc' in call.args[0]
        )
        self.assertIn("r.estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE')", attendee_query)

    def test_instructor_dashboard_hides_class_participants_from_non_monitors(self):
        instructor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}
        with patch('api.views.dashboard._require_persona', return_value=(instructor, None)), \
                patch('api.views.dashboard._profile_ids', return_value={
                    'socio_id': None, 'instructor_id': 21,
                }), \
                patch('api.views.dashboard._row', return_value={'tipo': 'COACH'}), \
                patch('api.views.dashboard._rows', return_value=[]) as rows:
            response = self.client.get('/api/dashboard')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['instructor_sessions'], [])
        self.assertEqual(response.json()['attendees'], [])
        self.assertFalse(any('FROM reserva r JOIN sesion_clase sc' in call.args[0] for call in rows.call_args_list))

    def test_monitor_cannot_create_training_followups(self):
        monitor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}
        with patch('api.views.resources._require_persona', return_value=(monitor, None)), \
                patch('api.views.resources._profile_ids', return_value={
                    'socio_id': None, 'instructor_id': 21,
                }), \
                patch('api.views.resources._row', return_value={'tipo': 'MONITOR'}), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/followups',
                data=json.dumps({
                    'socio_id': 9,
                    'tipo': 'PLAN',
                    'titulo': 'Plan de entrenamiento',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 403)
        execute.assert_not_called()

    def test_non_monitor_followups_use_the_specialty_workspace_instead(self):
        instructor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}
        with patch('api.views.resources._require_persona', return_value=(instructor, None)), \
                patch('api.views.resources._profile_ids', return_value={
                    'socio_id': None, 'instructor_id': 21,
                }), \
                patch('api.views.resources._row', return_value={'tipo': 'COACH'}), \
                patch('api.views.resources._execute') as execute:
            response = self.client.post(
                '/api/followups',
                data=json.dumps({
                    'socio_id': 9,
                    'tipo': 'PLAN',
                    'titulo': 'Plan de acción',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 410)
        execute.assert_not_called()

    def test_only_monitors_can_record_class_attendance(self):
        instructor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}
        with patch('api.views.sessions._require_persona', return_value=(instructor, None)), \
                patch('api.views.sessions._profile_ids', return_value={
                    'socio_id': None, 'instructor_id': 21,
                }), \
                patch('api.views.sessions._row', return_value={'tipo': 'COACH'}), \
                patch('api.views.sessions._execute') as execute:
            response = self.client.post(
                '/api/sessions/7/attendance',
                data=json.dumps({'reserva_id': 4, 'asistio': True}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 403)
        execute.assert_not_called()

    def test_public_home_shows_dynamic_activity_container_and_registration_links(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="landing-activities"')
        self.assertContains(response, '/iniciar-sesion/?crear=1&amp;continuar=clases')

    def test_public_activity_listing_does_not_require_a_session(self):
        sessions = [{
            'sesion_id': 8,
            'nombre': 'Partido de fútbol',
            'actividad': 'Fútbol',
            'instructor': 'Alex',
            'sala': 'Cancha #1',
            'inicio': '2026-11-10T20:00:00-03:00',
            'fin': '2026-11-10T21:00:00-03:00',
            'estado': 'PROGRAMADA',
            'cupos_disponibles': 5,
            'precio': 0,
            'imagen_url': None,
        }]
        with patch('api.views.sessions._rows', return_value=sessions) as rows:
            response = self.client.get('/api/public/sessions')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sessions'], sessions)
        query = rows.call_args.args[0]
        self.assertIn("sc.estado = 'PROGRAMADA'", query)
        self.assertIn('sc.inicio >= CURRENT_TIMESTAMP', query)
        self.assertIn('ORDER BY sc.inicio ASC LIMIT 6', query)
        self.assertIn('sc.estado,', query)
        self.assertNotIn('v.cupos_disponibles > 0', query)


    def test_account_registration_does_not_issue_a_credential(self):
        with patch('api.views.auth._row', return_value={'rol_id': 4}), \
                patch('api.views.auth._execute', side_effect=[(9,), None, None, None]) as execute, \
                patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'clave-segura-123',
                    'rut': '12.345.678-5',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn('credential', response.json())
        self.assertEqual(execute.call_args_list[0].args[1][0], '123456785')
        self.assertFalse(any('credencial_qr' in call.args[0] for call in execute.call_args_list))

    def test_account_registration_normalizes_lowercase_k(self):
        with patch('api.views.auth._row', return_value={'rol_id': 4}), \
                patch('api.views.auth._execute', side_effect=[(9,), None, None, None]) as execute, \
                patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'clave-segura-123',
                    'rut': '1.000.005-k',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(execute.call_args_list[0].args[1][0], '1000005K')

    def test_credential_issuance_requires_a_current_membership(self):
        with patch('api.views.auth._require_persona', return_value=(self.member, None)), \
                patch('api.views.auth._profile_ids', return_value={'socio_id': 21}), \
                patch('api.views.auth._row', return_value={'vigente': False}), \
                patch('api.views.auth._execute') as execute, \
                patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            response = self.client.post('/api/auth/credential')

        self.assertEqual(response.status_code, 409)
        self.assertIn('membresía vigente', response.json()['error'])
        execute.assert_not_called()

    def test_qr_credential_requires_a_current_membership(self):
        with patch('api.views.auth._require_persona', return_value=(self.member, None)), \
                patch('api.views.auth._profile_ids', return_value={'socio_id': 21}), \
                patch('api.views.auth._row', return_value=None), \
                patch('api.views.auth._execute') as execute, \
                patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            response = self.client.post('/api/auth/credential/qr')

        self.assertEqual(response.status_code, 409)
        self.assertIn('membresía vigente', response.json()['error'])
        execute.assert_not_called()

    def test_instructor_can_generate_a_staff_qr_without_a_membership(self):
        instructor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}
        with patch('api.views.auth._require_persona', return_value=(instructor, None)), \
                patch('api.views.auth._profile_ids', return_value={'socio_id': None, 'instructor_id': 21}), \
                patch('api.views.auth._row', return_value={'instructor_id': 21}), \
                patch('api.views.auth._execute') as execute, \
                patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            response = self.client.post('/api/auth/credential/qr')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/svg+xml')
        self.assertTrue(any('credencial_personal_qr' in call.args[0] for call in execute.call_args_list))

    def test_staff_qr_is_validated_by_staff_access_function(self):
        admin = {'rut': '123456785', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.access._require_persona', return_value=(admin, None)), \
                patch('api.views.access._row', side_effect=[
                    {
                        'punto_acceso_id': 2,
                        'instalacion_id': 3,
                        'uso': 'GENERAL',
                        'tiene_estacionamiento': False,
                    },
                    {'evento_id': 4, 'resultado': 'AUTORIZADO', 'motivo_rechazo': None},
                ]) as row:
            response = self.client.post(
                '/api/access/validate',
                data=json.dumps({
                    'credential': 'FITLIFE-STAFF:secret-token',
                    'punto_acceso_id': 2,
                    'tipo': 'ENTRADA',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn('registrar_acceso_personal_qr', row.call_args_list[1].args[0])
        self.assertEqual(row.call_args.args[1], ('secret-token', 2, 'ENTRADA'))

    def test_receptionist_cannot_validate_access_at_another_site(self):
        receptionist = {
            'rut': '123456785',
            'roles': ['RECEPCIONISTA'],
            'recepcionista_instalacion_id': 3,
        }
        with patch('api.views.access._require_persona', return_value=(receptionist, None)), \
                patch('api.views.access._row', return_value={
                    'punto_acceso_id': 2,
                    'instalacion_id': 4,
                    'uso': 'GENERAL',
                    'tiene_estacionamiento': False,
                }) as row:
            response = self.client.post(
                '/api/access/validate',
                data=json.dumps({
                    'credential': 'member-token',
                    'punto_acceso_id': 2,
                    'tipo': 'ENTRADA',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 403)
        self.assertIn('sede asignada', response.json()['error'])
        row.assert_called_once()
        self.assertIn('tiene_estacionamiento', row.call_args.args[0])

    def test_parking_access_is_rejected_if_site_parking_is_disabled(self):
        admin = {'rut': '123456785', 'roles': ['ADMINISTRADOR']}
        with patch('api.views.access._require_persona', return_value=(admin, None)), \
                patch('api.views.access._row', return_value={
                    'punto_acceso_id': 2,
                    'instalacion_id': 4,
                    'uso': 'ESTACIONAMIENTO',
                    'tiene_estacionamiento': False,
                }) as row:
            response = self.client.post(
                '/api/access/validate',
                data=json.dumps({
                    'credential': 'member-token',
                    'punto_acceso_id': 2,
                    'tipo': 'ENTRADA',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('no cuenta con estacionamiento', response.json()['error'])
        row.assert_called_once()

    def test_unassigned_receptionist_cannot_validate_access(self):
        receptionist = {'rut': '123456785', 'roles': ['RECEPCIONISTA']}
        with patch('api.views.access._require_persona', return_value=(receptionist, None)), \
                patch('api.views.access._row') as row:
            response = self.client.post(
                '/api/access/validate',
                data=json.dumps({
                    'credential': 'member-token',
                    'punto_acceso_id': 2,
                    'tipo': 'ENTRADA',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 403)
        row.assert_not_called()


class ReceptionSiteRoleTests(SimpleTestCase):
    admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}

    def test_admin_can_create_receptionist_with_one_site(self):
        with patch('api.views.staff._require_persona', return_value=(self.admin, None)), \
                patch('api.views.staff._row', side_effect=[
                    {'instalacion_id': 4},
                    {'rol_id': 2},
                ]), patch('api.views.staff._execute', side_effect=[
                    ('123456785',), None, None, None,
                ]) as execute, \
                patch('api.views.staff.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/users',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'clave-segura-123',
                    'rut': '12.345.678-5',
                    'rol': 'RECEPCIONISTA',
                    'instalacion_id': 4,
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        assignment = next(call for call in execute.call_args_list if 'recepcionista_sede' in call.args[0])
        self.assertEqual(assignment.args[1], ('123456785', 4))

    def test_assigning_receptionist_role_requires_active_site(self):
        with patch('api.views.staff._require_persona', return_value=(self.admin, None)), \
                patch('api.views.staff._row') as row, \
                patch('api.views.staff._execute') as execute:
            response = self.client.patch(
                '/api/users/123456785/roles',
                data=json.dumps({
                    'roles': ['RECEPCIONISTA'],
                    'tipo_profesional': '',
                    'especialidad': '',
                    'instalacion_id': None,
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('sede seleccionada', response.json()['error'])
        row.assert_not_called()
        execute.assert_not_called()

    def test_admin_can_assign_receptionist_to_one_site(self):
        with patch('api.views.staff._require_persona', return_value=(self.admin, None)), \
                patch('api.views.staff._row', side_effect=[
                    {'instalacion_id': 4},
                    {'rut': '123456785', 'activo': True},
                ]), patch('api.views.staff._rows', side_effect=[
                    [],
                    [{'rol_id': 2, 'codigo': 'RECEPCIONISTA'}],
                ]), patch('api.views.staff._execute') as execute, \
                patch('api.views.staff.transaction.atomic', return_value=nullcontext()):
            response = self.client.patch(
                '/api/users/123456785/roles',
                data=json.dumps({
                    'roles': ['RECEPCIONISTA'],
                    'tipo_profesional': '',
                    'especialidad': '',
                    'instalacion_id': 4,
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        assignment = next(call for call in execute.call_args_list if 'recepcionista_sede' in call.args[0])
        self.assertIn('ON CONFLICT (rut) DO UPDATE', assignment.args[0])
        self.assertEqual(assignment.args[1], ('123456785', 4))


class ProfessionalWorkspaceApiTests(SimpleTestCase):
    instructor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}

    def test_monitor_workspace_does_not_expose_individual_training_tools(self):
        with patch('api.views.professional._require_persona', return_value=(self.instructor, None)), \
                patch('api.views.professional._profile_ids', return_value={'instructor_id': 21}), \
                patch('api.views.professional._row', return_value={'tipo': 'MONITOR'}), \
                patch('api.views.professional._rows', return_value=[]) as rows:
            response = self.client.get('/api/professional/workspace')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['specialty'], 'MONITOR')
        self.assertEqual(response.json()['assigned_members'], [])
        self.assertNotIn('evaluations', response.json())
        self.assertNotIn('plans', response.json())
        self.assertEqual(rows.call_count, 1)

    def test_professional_cannot_write_for_unassigned_member(self):
        with patch('api.views.professional._require_persona', return_value=(self.instructor, None)), \
                patch('api.views.professional._profile_ids', return_value={'instructor_id': 21}), \
                patch('api.views.professional._row', side_effect=[
                    {'tipo': 'PERSONAL_TRAINER'}, None,
                ]), patch('api.views.professional._execute') as execute, \
                patch('api.views.professional.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/professional/workspace',
                data=json.dumps({
                    'accion': 'EVALUACION_INICIAL',
                    'socio_id': 9,
                    'objetivo': 'Aumentar fuerza',
                    'condicion_inicial': 'Nivel inicial',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 403)
        execute.assert_not_called()

    def test_trainer_plan_persists_routine_and_exercise_details(self):
        with patch('api.views.professional._require_persona', return_value=(self.instructor, None)), \
                patch('api.views.professional._profile_ids', return_value={'instructor_id': 21}), \
                patch('api.views.professional._row', side_effect=[
                    {'tipo': 'PERSONAL_TRAINER'}, {'asignado': 1},
                ]), patch('api.views.professional._execute', side_effect=[
                    (31,), (5,), None, (6,), None,
                ]) as execute, \
                patch('api.views.professional.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/professional/workspace',
                data=json.dumps({
                    'accion': 'PLAN_ENTRENAMIENTO',
                    'socio_id': 9,
                    'titulo': 'Hipertrofia',
                    'objetivo': 'Aumentar masa muscular',
                    'fecha_inicio': '2025-01-01',
                    'rutinas': [{
                        'dia': 'Día 1',
                        'ejercicios': [{
                            'nombre': 'Sentadilla',
                            'series': 4,
                            'repeticiones': '8-10',
                            'carga_kg': '60',
                            'descanso_segundos': 90,
                        }],
                    }, {
                        'dia': 'Día 2',
                        'ejercicios': [{
                            'nombre': 'Press banca',
                            'series': 3,
                            'repeticiones': '10',
                        }],
                    }],
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(execute.call_count, 5)
        self.assertIn('INSERT INTO plan_entrenamiento', execute.call_args_list[0].args[0])
        self.assertIn('INSERT INTO ejercicio_entrenamiento', execute.call_args_list[2].args[0])
        self.assertEqual(execute.call_args_list[2].args[1][1:5], ('Sentadilla', 4, '8-10', Decimal('60')))
        self.assertIn('INSERT INTO ejercicio_entrenamiento', execute.call_args_list[4].args[0])

    def test_coach_cannot_create_personal_training_plan_action(self):
        with patch('api.views.professional._require_persona', return_value=(self.instructor, None)), \
                patch('api.views.professional._profile_ids', return_value={'instructor_id': 21}), \
                patch('api.views.professional._row', side_effect=[
                    {'tipo': 'COACH'}, {'asignado': 1},
                ]), patch('api.views.professional._execute') as execute, \
                patch('api.views.professional.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/professional/workspace',
                data=json.dumps({'accion': 'PLAN_ENTRENAMIENTO', 'socio_id': 9}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()


class MonitorClassPlanningApiTests(SimpleTestCase):
    monitor = {'rut': '123456785', 'roles': ['INSTRUCTOR']}

    def test_monitor_can_create_class_only_for_self_at_assigned_site(self):
        with patch('api.views.sessions._require_persona', return_value=(self.monitor, None)), \
                patch('api.views.sessions._profile_ids', return_value={'instructor_id': 21}), \
                patch('api.views.sessions._row', side_effect=[
                    {'tipo': 'MONITOR'}, {'asignada': 1}, {'permitido': 1},
                ]), patch('api.views.sessions._store_class_image', return_value=None), \
                patch('api.views.sessions._execute', side_effect=[(4,), (8,)]) as execute, \
                patch('api.views.sessions.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/sessions',
                data=json.dumps({
                    'actividad': 'Spinning',
                    'nombre': 'Spinning tarde',
                    'instalacion_id': 3,
                    'instructor_id': 999,
                    'sala_id': 5,
                    'cupos_totales': 12,
                    'inicio': '2099-01-02T18:00:00+00:00',
                    'fin': '2099-01-02T19:00:00+00:00',
                    'intensidad': 'ALTA',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        insert = execute.call_args_list[1]
        self.assertEqual(insert.args[1][1], 21)
        self.assertIn('descripcion_sesion, intensidad, observaciones', insert.args[0])

    def test_monitor_cannot_schedule_at_unassigned_site(self):
        with patch('api.views.sessions._require_persona', return_value=(self.monitor, None)), \
                patch('api.views.sessions._profile_ids', return_value={'instructor_id': 21}), \
                patch('api.views.sessions._row', side_effect=[
                    {'tipo': 'MONITOR'}, None,
                ]), patch('api.views.sessions._execute') as execute:
            response = self.client.post(
                '/api/sessions',
                data=json.dumps({
                    'actividad': 'Spinning',
                    'instalacion_id': 3,
                    'sala_id': 5,
                    'cupos_totales': 12,
                    'inicio': '2099-01-02T18:00:00+00:00',
                    'fin': '2099-01-02T19:00:00+00:00',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 403)
        execute.assert_not_called()

    def test_monitor_cannot_record_observations_on_another_instructors_class(self):
        with patch('api.views.sessions._require_persona', return_value=(self.monitor, None)), \
                patch('api.views.sessions._profile_ids', return_value={'instructor_id': 21}), \
                patch('api.views.sessions._row', side_effect=[
                    {'tipo': 'MONITOR'}, None,
                ]), patch('api.views.sessions._execute') as execute:
            response = self.client.post(
                '/api/sessions/8/observations',
                data=json.dumps({'observaciones': 'Clase completada'}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 403)
        execute.assert_not_called()


class ProfessionalAssignmentAdminApiTests(SimpleTestCase):
    admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}

    def test_admin_can_assign_non_monitor_professional_to_active_member(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data._row', side_effect=[
                    {'permitido': 1}, {'permitido': 1},
                ]), patch('api.views.admin_data._execute', return_value=(17,)) as execute, \
                patch('api.views.admin_data.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/admin/data/asignaciones-profesionales',
                data=json.dumps({'instructor_id': 21, 'socio_id': 9}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertIn('instructor_socio', execute.call_args.args[0])
        self.assertIn('ON CONFLICT', execute.call_args.args[0])
        self.assertEqual(execute.call_args.args[1][-1], self.admin['rut'])

    def test_admin_unassigns_without_deleting_professional_history(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data.transaction.atomic', return_value=nullcontext()), \
                patch('api.views.admin_data._execute', return_value=(21,)) as execute:
            response = self.client.delete('/api/admin/data/asignaciones-profesionales/21-9')

        self.assertEqual(response.status_code, 200)
        self.assertIn('UPDATE instructor_socio SET activo = FALSE', execute.call_args.args[0])

    def test_admin_cannot_assign_monitor_as_personal_supervisor(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data._row', return_value=None), \
                patch('api.views.admin_data._execute') as execute:
            response = self.client.post(
                '/api/admin/data/asignaciones-profesionales',
                data=json.dumps({'instructor_id': 21, 'socio_id': 9}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()


class LoginApiTests(SimpleTestCase):
    def test_login_accepts_email_and_normalizes_rut(self):
        user = {'rut': '1000005K', 'nombres': 'Ana', 'hash_contrasena': 'hashed'}
        for identifier, expected_query, expected_param in (
            ('ANA@EXAMPLE.TEST', 'LOWER(p.correo)', 'ana@example.test'),
            ('1.000.005-k', 'p.rut = %s', '1000005K'),
        ):
            with self.subTest(identifier=identifier), \
                    patch('api.views.auth._row', side_effect=[user, {'codigo': 'SOCIO'}]) as row, \
                    patch('api.views.auth._rows', return_value=[{'codigo': 'SOCIO'}]), \
                    patch('api.views.auth.check_password', return_value=True):
                response = self.client.post(
                    '/api/auth/login',
                    data=json.dumps({
                        'identificador': identifier,
                        'contrasena': 'secreta-segura-2026',
                    }),
                    content_type='application/json',
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['user']['rut'], '1000005K')
            self.assertIn(expected_query, row.call_args_list[0].args[0])
            self.assertEqual(row.call_args_list[0].args[1], (expected_param,))

    def test_login_rejects_invalid_rut_without_database_lookup(self):
        with patch('api.views.auth._row') as row:
            response = self.client.post(
                '/api/auth/login',
                data=json.dumps({'identificador': '12.345.678-4', 'contrasena': 'incorrecta'}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 401)
        row.assert_not_called()

    def test_account_registration_normalizes_phone_with_country_code(self):
        with patch('api.views.auth._row', side_effect=[None, {'rol_id': 4}]), \
                patch('api.views.auth._execute', side_effect=[(9,), None, None, None]) as execute, \
                patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'clave-segura-123',
                    'rut': '1000005K',
                    'telefono': '9 1234 5678',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(execute.call_args_list[0].args[1][-1], '+56912345678')

    def test_account_registration_rejects_duplicate_phone_before_database_writes(self):
        with patch('api.views.auth._row', return_value={'rut': '11111114'}), \
                patch('api.views.auth._execute') as execute:
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'clave-segura-123',
                    'rut': '1000005K',
                    'telefono': '9 1234 5678',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn('teléfono', response.json()['error'])
        execute.assert_not_called()

    def test_account_registration_rejects_invalid_phone_before_database_access(self):
        with patch('api.views.auth._row') as row:
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'clave-segura-123',
                    'rut': '1000005K',
                    'telefono': '12345',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('9 dígitos', response.json()['error'])
        row.assert_not_called()

    def test_account_registration_rejects_weak_password_before_database_access(self):
        with patch('api.views.auth._row') as row:
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'password123',
                    'rut': '1000005K',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('12 caracteres', response.json()['error'])
        row.assert_not_called()

    def test_account_registration_rejects_invalid_names_before_database_access(self):
        with patch('api.views.auth._row') as row:
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': '9',
                    'apellido_paterno': '+4494',
                    'correo': 'ana@example.test',
                    'contrasena': 'clave-segura-123',
                    'rut': '1000005K',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('nombre', response.json()['error'])
        row.assert_not_called()


class StaffNameValidationTests(SimpleTestCase):
    def test_staff_creation_rejects_non_letter_names_before_database_access(self):
        with patch('api.views.staff._require_persona', return_value=({'rut': '1000005K'}, None)), \
                patch('api.views.staff._row') as row:
            response = self.client.post(
                '/api/users',
                data=json.dumps({
                    'nombres': '9',
                    'apellido_paterno': '+4494',
                    'rut': '11111114',
                    'correo': 'staff@example.test',
                    'contrasena': 'clave-segura-123',
                    'rol': 'RECEPCIONISTA',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('nombre', response.json()['error'])
        row.assert_not_called()


class BootstrapAdminCommandTests(SimpleTestCase):
    def test_bootstrap_admin_supports_legacy_persona_columns(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ('persona', 'persona_id'),
            ('persona', 'documento_identidad'),
            ('usuario', 'persona_id'),
            ('usuario_rol', 'persona_id'),
        ]
        cursor.fetchone.side_effect = [None, None, (1,), (42,)]
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        database = MagicMock()
        database.cursor.return_value = cursor_manager

        with patch.dict('os.environ', {
            'FITLIFE_ADMIN_EMAIL': 'admin@example.test',
            'FITLIFE_ADMIN_PASSWORD': 'password-segura-123',
            'FITLIFE_ADMIN_RUT': '1.000.005-k',
        }), patch('api.management.commands.bootstrap_admin.connection', database), \
                patch('api.management.commands.bootstrap_admin.transaction.atomic', return_value=nullcontext()):
            BootstrapAdminCommand().handle()

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn(
            'INSERT INTO persona (documento_identidad, nombres, "apellidoPaterno", '
            '"apellidoMaterno", correo) VALUES (%s, %s, %s, %s, %s) RETURNING persona_id',
            statements,
        )
        self.assertIn(
            'INSERT INTO usuario (persona_id, hash_contrasena) VALUES (%s, %s)',
            statements,
        )
        self.assertIn(
            'INSERT INTO usuario_rol (persona_id, rol_id) VALUES (%s, %s)',
            statements,
        )
        self.assertEqual(cursor.execute.call_args_list[4].args[1][0], '1000005K')

    def test_bootstrap_admin_uses_rut_columns_when_available(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            ('persona', 'rut'),
            ('usuario', 'rut'),
            ('usuario_rol', 'rut'),
        ]
        cursor.fetchone.side_effect = [None, None, (1,), ('1000005K',)]
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        database = MagicMock()
        database.cursor.return_value = cursor_manager

        with patch.dict('os.environ', {
            'FITLIFE_ADMIN_EMAIL': 'admin@example.test',
            'FITLIFE_ADMIN_PASSWORD': 'password-segura-123',
            'FITLIFE_ADMIN_RUT': '1000005K',
        }), patch('api.management.commands.bootstrap_admin.connection', database), \
                patch('api.management.commands.bootstrap_admin.transaction.atomic', return_value=nullcontext()):
            BootstrapAdminCommand().handle()

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn(
            'INSERT INTO persona (rut, nombres, "apellidoPaterno", "apellidoMaterno", correo) '
            'VALUES (%s, %s, %s, %s, %s) RETURNING rut',
            statements,
        )
        self.assertIn('INSERT INTO usuario (rut, hash_contrasena) VALUES (%s, %s)', statements)
        self.assertIn('INSERT INTO usuario_rol (rut, rol_id) VALUES (%s, %s)', statements)


class AdminDataApiTests(SimpleTestCase):
    admin = {'rut': '1000005K', 'roles': ['ADMINISTRADOR']}

    def test_generic_installation_editor_uses_google_maps_link_instead_of_coordinates(self):
        fields = _entity_fields(ENTITIES['instalaciones'])
        map_field = next(field for field in fields if field['name'] == 'mapa_url')
        self.assertEqual(map_field['type'], 'google_maps_url')
        self.assertTrue(map_field['required'])
        region_field = next(field for field in fields if field['name'] == 'region')
        self.assertEqual(region_field['choices'], list(REGION_CITIES))
        city_field = next(field for field in fields if field['name'] == 'ciudad')
        self.assertEqual(city_field['type'], 'city')
        self.assertNotIn('latitud', {field['name'] for field in fields})
        self.assertNotIn('longitud', {field['name'] for field in fields})

    def test_plan_editor_offers_only_plan_and_membership_types(self):
        fields = _entity_fields(ENTITIES['planes'])
        type_field = next(field for field in fields if field['name'] == 'tipo')
        self.assertEqual(type_field['type'], 'choice')
        self.assertEqual(type_field['choices'], ['PLAN', 'MEMBRESIA'])

    def test_generic_installation_editor_requires_hours_and_accepts_chilean_coordinates(self):
        body = {
            'nombre': 'Fit Centro',
            'direccion': 'Compañía de Jesús 1214',
            'region': 'Metropolitana de Santiago',
            'ciudad': 'Santiago',
            'aforo_maximo': 200,
            'horario_lunes_viernes': '6h - 22h',
            'horario_sabados_dom_festivos': '8h - 16h',
            'mapa_url': 'https://maps.app.goo.gl/example',
            'tiene_lockers': False,
            'cantidad_lockers': 0,
            'tiene_estacionamiento': False,
            'cupos_estacionamiento': 0,
            'tiene_vestidores': False,
            'cantidad_vestidores': 0,
            'tiene_duchas': False,
            'cantidad_duchas': 0,
            'activa': True,
        }
        with patch(
            'api.views.admin_data.resolve_google_maps_url',
            return_value=(Decimal('-33.439035'), Decimal('-70.654187')),
        ):
            values = _validate_entity_values(ENTITIES['instalaciones'], body, creating=True)
        self.assertEqual(values['latitud'], Decimal('-33.439035'))
        self.assertEqual(values['longitud'], Decimal('-70.654187'))

        body.pop('horario_lunes_viernes')
        with self.assertRaisesMessage(ValueError, 'Horario · Lun a Vie'):
            _validate_entity_values(ENTITIES['instalaciones'], body, creating=True)

    def test_person_admin_form_rejects_numeric_names(self):
        with self.assertRaisesMessage(ValueError, 'Nombres'):
            _validate_entity_values(ENTITIES['personas'], {
                'rut': '1000005K',
                'nombres': '9',
                'apellidoPaterno': 'Rojas',
                'apellidoMaterno': '',
                'correo': 'ana@example.test',
            }, creating=True)

    def test_person_admin_form_normalizes_phone_for_unique_storage(self):
        values = _validate_entity_values(ENTITIES['personas'], {
            'rut': '1000005K',
            'nombres': 'Ana',
            'apellidoPaterno': 'Rojas',
            'apellidoMaterno': '',
            'correo': 'ana@example.test',
            'telefono': '9 1234 5678',
        }, creating=True)

        self.assertEqual(values['telefono'], '+56912345678')

    def test_person_patch_ignores_unchanged_rut_from_stale_admin_form(self):
        record_rut = '218578373'
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data.transaction.atomic', return_value=nullcontext()), \
                patch('api.views.admin_data._update_entity', return_value=True) as update:
            response = self.client.patch(
                f'/api/admin/data/personas/{record_rut}',
                data=json.dumps({
                    'rut': record_rut,
                    'correo': 'persona@example.test',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 200)
        update.assert_called_once_with(
            ENTITIES['personas'], record_rut, {'correo': 'persona@example.test'},
        )

    def test_person_patch_rejects_attempt_to_change_rut(self):
        record_rut = '218578373'
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data._update_entity') as update:
            response = self.client.patch(
                f'/api/admin/data/personas/{record_rut}',
                data=json.dumps({
                    'rut': '1000005K',
                    'correo': 'persona@example.test',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('identificador', response.json()['error'])
        update.assert_not_called()

    def test_admin_entity_list_excludes_payment_and_history_tables(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)):
            response = self.client.get('/api/admin/data')

        self.assertEqual(response.status_code, 200)
        entities = {item['key'] for item in response.json()['entities']}
        self.assertNotIn('pago', entities)
        self.assertNotIn('pago_reserva', entities)
        self.assertNotIn('evento_acceso', entities)
        self.assertIn('reservas', entities)
        self.assertIn('credenciales-qr', entities)

    def test_admin_data_rejects_non_admin_users(self):
        error = JsonResponse({'error': 'No tienes permisos.'}, status=403)
        with patch('api.views.admin_data._require_persona', return_value=(None, error)):
            denied = self.client.get('/api/admin/data')
        self.assertEqual(denied.status_code, 403)

    def test_admin_data_rejects_unknown_or_protected_tables(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)):
            response = self.client.get('/api/admin/data/pagos')

        self.assertEqual(response.status_code, 404)
        self.assertIn('no está disponible', response.json()['error'])

    def test_admin_data_validates_enum_values_before_database_write(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data._execute') as execute:
            response = self.client.post(
                '/api/admin/data/puntos-acceso',
                data=json.dumps({
                    'instalacion_id': 1,
                    'nombre': 'Acceso norte',
                    'tipo': 'INVALIDO',
                    'activo': True,
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        execute.assert_not_called()

    def test_admin_cannot_edit_a_session_into_the_past(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data._execute') as execute:
            response = self.client.patch(
                '/api/admin/data/clases/12',
                data=json.dumps({
                    'inicio': '2020-01-01T10:00',
                    'fin': '2020-01-01T11:00',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('futuro', response.json()['error'])
        execute.assert_not_called()

    def test_generic_admin_manager_memberships_are_read_only(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data._execute') as execute:
            for method in (self.client.post, self.client.patch, self.client.delete):
                response = method(
                    '/api/admin/data/membresias',
                    data=json.dumps({'estado': 'ACTIVA'}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 405)
        execute.assert_not_called()

    def test_admin_account_crud_hashes_password_before_insert(self):
        with patch('api.views.admin_data._require_persona', return_value=(self.admin, None)), \
                patch('api.views.admin_data.transaction.atomic', return_value=nullcontext()), \
                patch('api.views.admin_data._execute', return_value=(21,)) as execute:
            response = self.client.post(
                '/api/admin/data/cuentas',
                data=json.dumps({'rut': '1000005K', 'activo': True, 'contrasena': 'secreta-segura-2026'}),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 201)
        sql, params = execute.call_args.args
        self.assertIn('hash_contrasena', sql)
        self.assertNotIn('secreta-segura-2026', params)
        self.assertNotEqual(params[-1], 'secreta-segura-2026')

    def test_all_declared_tables_have_column_allowlists(self):
        for key, entity in ENTITIES.items():
            with self.subTest(entity=key):
                self.assertTrue(entity['table'])
                self.assertTrue(entity['pk'])
                self.assertTrue(entity['columns'])
        tables = {entity['table'] for entity in ENTITIES.values()}
        self.assertEqual(tables, {
            'persona', 'usuario', 'rol', 'usuario_rol', 'socio', 'instructor',
            'perfil_instructor', 'plan_membresia', 'membresia', 'congelacion_membresia',
            'instalacion', 'punto_acceso', 'credencial_qr', 'actividad', 'sala',
            'sesion_clase', 'reserva', 'maquina', 'seguimiento_entrenamiento',
            'configuracion_gimnasio', 'prueba_socio', 'instructor_socio',
        })

    def test_person_relations_use_rut_in_admin_configuration(self):
        for key in ('cuentas', 'asignaciones-rol', 'socios', 'instructores', 'pruebas-socio'):
            entity = ENTITIES[key]
            with self.subTest(entity=key):
                self.assertNotEqual(entity['pk'], 'persona_id')
                self.assertNotIn('persona_id', entity['columns'])
                self.assertNotIn('persona_id', [field[0] for field in entity['fields']])


class JwtTests(SimpleTestCase):
    def test_execute_returns_none_when_statement_has_no_result_rows(self):
        cursor = MagicMock(description=None)
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        fake_connection = MagicMock()
        fake_connection.cursor.return_value = cursor_manager

        with patch('api.views.common.connection', fake_connection):
            result = _execute('INSERT INTO usuario (rut) VALUES (%s)', ('1000005K',))

        self.assertIsNone(result)
        cursor.fetchone.assert_not_called()

    def test_execute_fetches_result_rows_when_statement_returns_them(self):
        cursor = MagicMock()
        cursor.description = [('rut',)]
        cursor.fetchone.return_value = ('1000005K',)
        cursor_manager = MagicMock()
        cursor_manager.__enter__.return_value = cursor
        fake_connection = MagicMock()
        fake_connection.cursor.return_value = cursor_manager

        with patch('api.views.common.connection', fake_connection):
            result = _execute('INSERT INTO persona (rut, nombres) VALUES (%s, %s) RETURNING rut', ('1000005K', 'Ana'))

        self.assertEqual(result, ('1000005K',))
        cursor.fetchone.assert_called_once_with()

    def test_issued_token_contains_rut_subject(self):
        token = issue_token('1000005K')
        self.assertEqual(decode_token(token), '1000005K')

    def test_tampered_token_is_rejected(self):
        token = issue_token('1000005K')
        header, payload, signature = token.split('.')
        changed_payload = payload[:-1] + ('A' if payload[-1] != 'A' else 'B')
        self.assertIsNone(decode_token(f'{header}.{changed_payload}.{signature}'))

    def test_expired_token_is_rejected(self):
        encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')
        header = encode(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())
        payload = encode(json.dumps({'sub': '42', 'iat': int(time.time()) - 20, 'exp': int(time.time()) - 1}).encode())
        message = f'{header}.{payload}'.encode('ascii')
        signature = encode(hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).digest())
        self.assertIsNone(decode_token(f'{header}.{payload}.{signature}'))

    def test_malformed_token_is_rejected(self):
        self.assertIsNone(decode_token('not.a.jwt.token'))
        self.assertIsNone(decode_token(''))

    def test_registration_rejects_invalid_email_before_database_access(self):
        response = self.client.post(
            '/api/auth/register',
            data=json.dumps({
                'nombres': 'Ana',
                'apellido_paterno': 'Rojas',
                'rut': '1000005K',
                'correo': 'no-es-un-correo',
                'contrasena': 'una-clave-segura-123',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('correo', response.json()['error'])

    def test_registration_rejects_invalid_rut_before_database_access(self):
        with patch('api.views.auth._execute') as execute:
            response = self.client.post(
                '/api/auth/register',
                data=json.dumps({
                    'nombres': 'Ana',
                    'apellido_paterno': 'Rojas',
                    'correo': 'ana@example.test',
                    'contrasena': 'una-clave-segura-123',
                    'rut': '12.345.678-4',
                }),
                content_type='application/json',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('RUT', response.json()['error'])
        execute.assert_not_called()

    def test_registration_database_error_does_not_disclose_infrastructure(self):
        with patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            with patch('api.views.auth._row', side_effect=DatabaseError('PostgreSQL fit_db schema failure')):
                response = self.client.post(
                    '/api/auth/register',
                    data=json.dumps({
                        'nombres': 'Ana',
                        'apellido_paterno': 'Rojas',
                        'rut': '1000005K',
                        'correo': 'ana@example.com',
                        'contrasena': 'una-clave-segura-123',
                    }),
                    content_type='application/json',
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()['error'],
            'No fue posible completar la solicitud. Inténtalo nuevamente más tarde.',
        )
        self.assertNotIn('PostgreSQL', response.content.decode())
        self.assertNotIn('fit_db', response.content.decode())
        self.assertNotIn('schema', response.content.decode())

    def test_registration_missing_role_uses_generic_error(self):
        with patch('api.views.auth.transaction.atomic', return_value=nullcontext()):
            with patch('api.views.auth._row', return_value=None):
                response = self.client.post(
                    '/api/auth/register',
                    data=json.dumps({
                        'nombres': 'Ana',
                        'apellido_paterno': 'Rojas',
                        'rut': '1000005K',
                        'correo': 'ana@example.com',
                        'contrasena': 'una-clave-segura-123',
                    }),
                    content_type='application/json',
                )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn('SOCIO', response.content.decode())
        self.assertNotIn('esquema', response.content.decode())


class PortalPageTests(SimpleTestCase):
    def test_landing_page_uses_fitlife_template(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Encuentra tu próxima clase')
        self.assertContains(response, 'landing-plans')
        self.assertContains(response, 'href="/sedes/"')
        self.assertNotContains(response, 'landing-gym-locations')
        self.assertNotContains(response, 'gym-search-input')
        self.assertContains(response, 'public-footer-main')
        self.assertContains(response, 'href="/sedes/">Encuentra tu sede')
        self.assertContains(response, 'Clases y horarios')
        self.assertContains(response, 'Volver arriba')
        self.assertContains(response, 'aria-label="Accesos rápidos"')
        self.assertContains(response, 'aria-labelledby="activities-title"')
        self.assertContains(response, 'Saltar al contenido')
        self.assertNotContains(response, 'Hay más de una')
        self.assertNotContains(response, '>Spinning</h3>')
        self.assertNotContains(response, '>Yoga</h3>')
        self.assertContains(response, 'landing-hero')
        self.assertNotContains(response, 'landing-art')
        self.assertNotContains(response, 'gym-hero.svg')
        self.assertNotContains(response, 'Tu próxima meta')
        self.assertNotContains(response, 'Spinning · Yoga · Funcional')
        self.assertNotContains(response, 'Descubre FitLife')
        self.assertNotContains(response, 'proof-avatars')
        stylesheet = settings.BASE_DIR.joinpath(
            'templates', 'views', 'css', 'fitlife-public.css'
        ).read_text(encoding='utf-8')
        self.assertIn('url("../images/fitlife-gym.jpg")', stylesheet)
        self.assertIn('background-image:', stylesheet)
        self.assertContains(response, 'css/fitlife.css')
        self.assertContains(response, 'css/fitlife-public.css')
        self.assertContains(response, 'css/fitlife-dashboard.css')
        self.assertContains(response, 'home.js')

    def test_gym_directory_has_a_dedicated_page(self):
        response = self.client.get('/sedes/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SEDES FITLIFE')
        self.assertContains(response, 'Encuentra dónde')
        self.assertContains(response, 'gym-search-input')
        self.assertContains(response, 'landing-gym-locations')
        self.assertContains(response, 'public-gym-modal')
        self.assertContains(response, 'public-footer-main')
        self.assertContains(response, 'Iniciar sesión')
        self.assertContains(response, 'public-profile')
        self.assertContains(response, 'public-sidebar')
        self.assertContains(response, 'public-drawer-guest')
        self.assertContains(response, 'public-drawer-member')
        self.assertContains(response, 'public-logout')
        self.assertContains(response, 'home.js')

    def test_authentication_page_has_login_and_registration_forms(self):
        response = self.client.get('/iniciar-sesion/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Inicia sesión')
        self.assertContains(response, 'Crear cuenta')
        self.assertContains(response, 'Correo electrónico o RUT')

    def test_portal_shell_loads_for_javascript_authentication(self):
        response = self.client.get('/panel/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'js/vendor/jsQR.js?v=1.4.0')
        self.assertContains(response, 'dashboard.js?v=20261110-modular-dashboard')
        self.assertContains(response, 'type="module"')
        self.assertContains(response, 'fitlife-wordmark')
        self.assertContains(response, 'fitlife-public.css?v=20261110-fitlife-wordmark')
        self.assertContains(response, 'fitlife-dashboard.css?v=20261110-schedule-text-fields')
        self.assertContains(response, 'id="trial-confirmation"')

# Create your tests here.
