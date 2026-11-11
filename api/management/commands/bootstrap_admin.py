import os
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import DatabaseError, connection, transaction

from ...passwords import validate_account_password
from ...rut import normalize_rut


class Command(BaseCommand):
    help = 'Crea la cuenta administradora inicial de FitLife.'

    def handle(self, *args, **options):
        email = os.environ.get('FITLIFE_ADMIN_EMAIL', 'admin@fitlife.cl').strip().lower()
        try:
            validate_email(email)
        except ValidationError as error:
            raise CommandError('FITLIFE_ADMIN_EMAIL no es un correo válido.') from error

        password = os.environ.get('FITLIFE_ADMIN_PASSWORD')
        generated_password = not password
        if generated_password:
            if os.environ.get('DJANGO_DEBUG', 'true').lower() != 'true':
                raise CommandError('Define FITLIFE_ADMIN_PASSWORD en el entorno antes de crear el administrador.')
            password = secrets.token_urlsafe(32)
            self._save_local_credentials(email, password)

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    schema_columns = self._schema_columns(cursor)
                    if ('persona', 'rut') in schema_columns:
                        person_key = 'rut'
                        person_rut_column = 'rut'
                    elif {
                        ('persona', 'persona_id'),
                        ('persona', 'documento_identidad'),
                    }.issubset(schema_columns):
                        person_key = 'persona_id'
                        person_rut_column = 'documento_identidad'
                    else:
                        raise CommandError(
                            'El esquema de personas no es compatible. Aplica los esquemas SQL de FitLife.'
                        )

                    user_person_column = self._relation_column(schema_columns, 'usuario')
                    role_person_column = self._relation_column(schema_columns, 'usuario_rol')
                    cursor.execute(
                        f'SELECT p.{person_key}, EXISTS ('
                        'SELECT 1 FROM usuario_rol ur JOIN rol r USING (rol_id) '
                        f'WHERE ur.{role_person_column} = p.{person_key} AND r.codigo = %s'
                        f') FROM persona p WHERE LOWER(p.correo) = %s FOR UPDATE',
                        ('ADMINISTRADOR', email),
                    )
                    existing = cursor.fetchone()
                    if existing:
                        if existing[1]:
                            self.stdout.write(self.style.SUCCESS(
                                f'La cuenta administradora {email} ya existe.'
                            ))
                            return
                        raise CommandError(
                            'Ese correo ya pertenece a una cuenta FitLife que no es administradora.'
                        )

                    cursor.execute(
                        'SELECT 1 FROM usuario_rol ur JOIN rol r USING (rol_id) '
                        'WHERE r.codigo = %s LIMIT 1',
                        ('ADMINISTRADOR',),
                    )
                    if cursor.fetchone():
                        raise CommandError(
                            'Ya existe una cuenta administradora. No se creó otra por seguridad.'
                        )

                    cursor.execute('SELECT rol_id FROM rol WHERE codigo = %s', ('ADMINISTRADOR',))
                    role = cursor.fetchone()
                    if role is None:
                        raise CommandError(
                            'No está disponible el rol administrador. Aplica los esquemas SQL de FitLife.'
                        )

                    raw_rut = os.environ.get('FITLIFE_ADMIN_RUT', '').strip()
                    try:
                        admin_rut = normalize_rut(raw_rut)
                    except ValueError as error:
                        raise CommandError(
                            'Define FITLIFE_ADMIN_RUT con un RUT válido antes de crear el administrador.'
                        ) from error
                    try:
                        validate_account_password(password, get_user_model()(
                            username=admin_rut,
                            email=email,
                            first_name='Administrador',
                            last_name='FitLife',
                        ))
                    except ValueError as error:
                        raise CommandError(str(error)) from error
                    cursor.execute(
                        f'INSERT INTO persona ({person_rut_column}, nombres, "apellidoPaterno", '
                        f'"apellidoMaterno", correo) VALUES (%s, %s, %s, %s, %s) RETURNING {person_key}',
                        (admin_rut, 'Administrador', 'FitLife', '-', email),
                    )
                    person_id = cursor.fetchone()[0]
                    cursor.execute(
                        f'INSERT INTO usuario ({user_person_column}, hash_contrasena) VALUES (%s, %s)',
                        (person_id, make_password(password)),
                    )
                    cursor.execute(
                        f'INSERT INTO usuario_rol ({role_person_column}, rol_id) VALUES (%s, %s)',
                        (person_id, role[0]),
                    )
        except DatabaseError as error:
            raise CommandError(
                'No fue posible crear el administrador en la base de datos configurada. '
                f'Detalle técnico: {error}'
            ) from error

        self.stdout.write(self.style.SUCCESS(f'Cuenta administradora creada: {email}'))
        if generated_password:
            self.stdout.write(
                'La contraseña aleatoria quedó guardada en .env como FITLIFE_ADMIN_PASSWORD.'
            )

    @staticmethod
    def _schema_columns(cursor):
        cursor.execute(
            'SELECT table_name, column_name FROM information_schema.columns '
            'WHERE table_schema = current_schema() '
            "AND table_name IN ('persona', 'usuario', 'usuario_rol')"
        )
        return set(cursor.fetchall())

    @staticmethod
    def _relation_column(schema_columns, table):
        for column in ('rut', 'persona_id'):
            if (table, column) in schema_columns:
                return column
        raise CommandError(
            f'No se encontró la columna de relación de personas en {table}. '
            'Aplica los esquemas SQL de FitLife.'
        )

    @staticmethod
    def _save_local_credentials(email, password):
        env_path = Path(settings.BASE_DIR) / '.env'
        if not env_path.exists():
            raise CommandError(
                'No existe .env; define FITLIFE_ADMIN_PASSWORD manualmente antes de continuar.'
            )

        updates = {
            'FITLIFE_ADMIN_EMAIL': email,
            'FITLIFE_ADMIN_PASSWORD': password,
        }
        lines = env_path.read_text(encoding='utf-8').splitlines()
        remaining = set(updates)
        for index, line in enumerate(lines):
            key = line.split('=', 1)[0].strip()
            if key in updates:
                lines[index] = f'{key}={updates[key]}'
                remaining.discard(key)
        lines.extend(f'{key}={updates[key]}' for key in remaining)
        env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
