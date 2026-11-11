-- FitLife 1.14: usa rut como clave primaria de persona y conserva las relaciones.
BEGIN;
SET LOCAL search_path TO fitlife, public;

DROP VIEW IF EXISTS vw_disponibilidad_clases;
DROP VIEW IF EXISTS vw_lista_espera;
DROP VIEW IF EXISTS vw_membresias;
DROP VIEW IF EXISTS vw_accesos_recientes;
DROP VIEW IF EXISTS vw_aforo_actual;

DO $$
DECLARE
    has_legacy_persona_id BOOLEAN;
    has_unmapped_records BOOLEAN;
    child_table TEXT;
    constraint_name TEXT;
    child_tables TEXT[] := ARRAY['usuario_rol', 'prueba_socio', 'usuario', 'socio', 'instructor'];
BEGIN
    FOREACH child_table IN ARRAY child_tables LOOP
        IF to_regclass(format('fitlife.%I', child_table)) IS NULL THEN
            CONTINUE;
        END IF;
        FOR constraint_name IN
            SELECT constraint_row.conname
            FROM pg_constraint constraint_row
            JOIN pg_attribute column_row
              ON column_row.attrelid = constraint_row.conrelid
             AND column_row.attname = 'persona_id'
            WHERE constraint_row.conrelid = to_regclass(format('fitlife.%I', child_table))
              AND constraint_row.contype <> 'n'
              AND constraint_row.conkey @> ARRAY[column_row.attnum]::SMALLINT[]
        LOOP
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', child_table, constraint_name);
        END LOOP;
    END LOOP;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fitlife' AND table_name = 'persona' AND column_name = 'rut'
    ) THEN
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'fitlife' AND table_name = 'persona'
              AND column_name = 'documento_identidad'
        ) THEN
            ALTER TABLE persona RENAME COLUMN documento_identidad TO rut;
        ELSE
            RAISE EXCEPTION 'No se encontró persona.rut ni persona.documento_identidad para migrar las claves.';
        END IF;
    ELSIF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fitlife' AND table_name = 'persona'
          AND column_name = 'documento_identidad'
    ) THEN
        UPDATE persona
        SET rut = COALESCE(NULLIF(BTRIM(rut), ''), NULLIF(BTRIM(documento_identidad), ''));
    END IF;

    UPDATE persona
    SET rut = UPPER(REGEXP_REPLACE(BTRIM(rut), '[.\s-]', '', 'g'));
    IF EXISTS (SELECT 1 FROM persona WHERE rut IS NULL OR BTRIM(rut) = '') THEN
        RAISE EXCEPTION 'Hay personas sin RUT. Completa esos RUT antes de aplicar esta migración.';
    END IF;
    IF EXISTS (SELECT rut FROM persona GROUP BY rut HAVING COUNT(*) > 1) THEN
        RAISE EXCEPTION 'Hay RUT duplicados después de normalizarlos. Corrige esos registros antes de migrar.';
    END IF;
    ALTER TABLE persona ALTER COLUMN rut SET NOT NULL;

    has_legacy_persona_id := EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'fitlife' AND table_name = 'persona'
          AND column_name = 'persona_id'
    );

    FOREACH child_table IN ARRAY child_tables LOOP
        IF to_regclass(format('fitlife.%I', child_table)) IS NULL THEN
            CONTINUE;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'fitlife' AND table_name = child_table
              AND column_name = 'persona_id'
        ) THEN
            CONTINUE;
        END IF;

        EXECUTE format('ALTER TABLE %I ADD COLUMN _rut_migracion VARCHAR(30)', child_table);
        IF has_legacy_persona_id THEN
            EXECUTE format(
                'UPDATE %I child SET _rut_migracion = person.rut '
                'FROM persona person WHERE child.persona_id::TEXT = person.persona_id::TEXT',
                child_table
            );
        ELSE
            EXECUTE format(
                'UPDATE %I child SET _rut_migracion = person.rut '
                'FROM persona person WHERE UPPER(REGEXP_REPLACE(BTRIM(child.persona_id::TEXT), %L, %L, %L)) = person.rut',
                child_table, '[.\s-]', '', 'g'
            );
        END IF;
        EXECUTE format(
            'SELECT EXISTS (SELECT 1 FROM %I WHERE persona_id IS NOT NULL AND _rut_migracion IS NULL)',
            child_table
        ) INTO has_unmapped_records;
        IF has_unmapped_records THEN
            RAISE EXCEPTION 'No se pudo asociar cada registro de % con un RUT. No se aplicaron cambios.', child_table;
        END IF;

        FOR constraint_name IN
            SELECT constraint_row.conname
            FROM pg_constraint constraint_row
            JOIN pg_attribute column_row
              ON column_row.attrelid = constraint_row.conrelid
             AND column_row.attname = 'persona_id'
            WHERE constraint_row.conrelid = to_regclass(format('fitlife.%I', child_table))
              AND constraint_row.contype <> 'n'
              AND constraint_row.conkey @> ARRAY[column_row.attnum]::SMALLINT[]
        LOOP
            EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', child_table, constraint_name);
        END LOOP;

        EXECUTE format('ALTER TABLE %I DROP COLUMN persona_id', child_table);
        EXECUTE format('ALTER TABLE %I RENAME COLUMN _rut_migracion TO persona_id', child_table);
    END LOOP;

    FOR constraint_name IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'fitlife.persona'::regclass
          AND contype = 'p'
          AND conkey @> ARRAY[(
              SELECT attnum FROM pg_attribute
              WHERE attrelid = 'fitlife.persona'::regclass AND attname = 'persona_id'
          )]::SMALLINT[]
    LOOP
        EXECUTE format('ALTER TABLE persona DROP CONSTRAINT %I', constraint_name);
    END LOOP;

    ALTER TABLE persona DROP COLUMN IF EXISTS persona_id;
    ALTER TABLE persona DROP COLUMN IF EXISTS documento_identidad;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint constraint_row
        WHERE constraint_row.conrelid = 'fitlife.persona'::regclass
          AND constraint_row.contype = 'p'
          AND constraint_row.conkey @> ARRAY[(
              SELECT attnum FROM pg_attribute
              WHERE attrelid = 'fitlife.persona'::regclass AND attname = 'rut'
          )]::SMALLINT[]
    ) THEN
        ALTER TABLE persona ADD CONSTRAINT persona_pkey PRIMARY KEY (rut);
    END IF;

    ALTER TABLE usuario ADD CONSTRAINT usuario_pkey PRIMARY KEY (persona_id);
    ALTER TABLE usuario_rol ADD CONSTRAINT usuario_rol_pkey PRIMARY KEY (persona_id, rol_id);
    ALTER TABLE socio ALTER COLUMN persona_id SET NOT NULL;
    ALTER TABLE socio ADD CONSTRAINT socio_persona_id_key UNIQUE (persona_id);
    ALTER TABLE instructor ALTER COLUMN persona_id SET NOT NULL;
    ALTER TABLE instructor ADD CONSTRAINT instructor_persona_id_key UNIQUE (persona_id);
    IF to_regclass('fitlife.prueba_socio') IS NOT NULL THEN
        ALTER TABLE prueba_socio ADD CONSTRAINT prueba_socio_pkey PRIMARY KEY (persona_id);
    END IF;

    ALTER TABLE usuario
        ADD CONSTRAINT usuario_persona_id_fkey
        FOREIGN KEY (persona_id) REFERENCES persona(rut) ON DELETE RESTRICT;
    ALTER TABLE usuario_rol
        ADD CONSTRAINT usuario_rol_persona_id_fkey
        FOREIGN KEY (persona_id) REFERENCES usuario(persona_id) ON DELETE CASCADE;
    ALTER TABLE socio
        ADD CONSTRAINT socio_persona_id_fkey
        FOREIGN KEY (persona_id) REFERENCES persona(rut) ON DELETE RESTRICT;
    ALTER TABLE instructor
        ADD CONSTRAINT instructor_persona_id_fkey
        FOREIGN KEY (persona_id) REFERENCES persona(rut) ON DELETE RESTRICT;
    IF to_regclass('fitlife.prueba_socio') IS NOT NULL THEN
        ALTER TABLE prueba_socio
            ADD CONSTRAINT prueba_socio_persona_id_fkey
            FOREIGN KEY (persona_id) REFERENCES socio(persona_id) ON DELETE RESTRICT;
    END IF;
END
$$;

CREATE VIEW vw_disponibilidad_clases AS
SELECT sc.sesion_id, a.nombre AS actividad,
       CONCAT_WS(' ', pe.nombres, pe."apellidoPaterno", NULLIF(pe."apellidoMaterno", '-')) AS instructor,
       sa.nombre AS sala, sc.inicio, sc.fin, sc.estado, sc.cupos_totales,
       COUNT(r.reserva_id) FILTER (WHERE r.estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE'))::INTEGER AS cupos_ocupados,
       GREATEST(sc.cupos_totales - COUNT(r.reserva_id) FILTER (
           WHERE r.estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE')
       )::INTEGER, 0) AS cupos_disponibles,
       COUNT(r.reserva_id) FILTER (WHERE r.estado = 'EN_ESPERA')::INTEGER AS personas_en_espera,
       sc.precio, sc.nombre_sesion AS nombre
FROM sesion_clase sc
JOIN actividad a USING (actividad_id)
JOIN instructor ins USING (instructor_id)
JOIN persona pe ON pe.rut = ins.persona_id
JOIN sala sa USING (sala_id)
LEFT JOIN reserva r USING (sesion_id)
GROUP BY sc.sesion_id, a.nombre, pe.nombres, pe."apellidoPaterno", pe."apellidoMaterno",
         sa.nombre, sc.inicio, sc.fin, sc.estado, sc.cupos_totales, sc.precio, sc.nombre_sesion;

CREATE VIEW vw_lista_espera AS
SELECT r.reserva_id, r.sesion_id, r.socio_id,
       pe.nombres || ' ' || pe."apellidoPaterno" || ' ' || pe."apellidoMaterno" AS socio,
       ROW_NUMBER() OVER (PARTITION BY r.sesion_id ORDER BY r.creada_en, r.reserva_id) AS posicion_espera,
       r.creada_en
FROM reserva r
JOIN socio s ON s.socio_id = r.socio_id
JOIN persona pe ON pe.rut = s.persona_id
WHERE r.estado = 'EN_ESPERA';

CREATE VIEW vw_membresias AS
SELECT m.membresia_id, m.socio_id,
       pe.nombres || ' ' || pe."apellidoPaterno" || ' ' || pe."apellidoMaterno" AS socio,
       pm.nombre AS plan, m.estado, m.fecha_inicio, m.fecha_fin, m.precio_acordado,
       CASE
           WHEN m.estado IN ('CANCELADA', 'PENDIENTE') THEN m.estado::TEXT
           WHEN m.fecha_fin < CURRENT_DATE THEN 'VENCIDA'
           WHEN EXISTS (
               SELECT 1 FROM congelacion_membresia c
               WHERE c.membresia_id = m.membresia_id
                 AND CURRENT_DATE >= c.fecha_inicio
                 AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
           ) THEN 'CONGELADA'
           ELSE 'ACTIVA'
       END AS estado_calculado,
       pm.incluye_entrenador_personal, pm.incluye_lockers, pm.otros_beneficios,
       pm.incluye_estacionamiento, m.instalacion_id, i.nombre AS sede
FROM membresia m
JOIN socio s ON s.socio_id = m.socio_id
JOIN persona pe ON pe.rut = s.persona_id
JOIN plan_membresia pm ON pm.plan_id = m.plan_id
LEFT JOIN instalacion i ON i.instalacion_id = m.instalacion_id;

CREATE VIEW vw_aforo_actual AS
SELECT i.instalacion_id, i.nombre AS instalacion, i.aforo_maximo,
       COUNT(p.persona_id)::INTEGER AS personas_presentes,
       GREATEST(i.aforo_maximo - COUNT(p.persona_id)::INTEGER, 0) AS cupos_disponibles,
       ROUND((COUNT(p.persona_id)::NUMERIC / NULLIF(i.aforo_maximo, 0)) * 100, 2) AS porcentaje_ocupacion
FROM instalacion i
LEFT JOIN (
    SELECT pa.instalacion_id, s.persona_id
    FROM presencia_actual pr
    JOIN evento_acceso ea ON ea.evento_id = pr.evento_entrada_id
    JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
    JOIN socio s ON s.socio_id = pr.socio_id
    UNION ALL
    SELECT pa.instalacion_id, ins.persona_id
    FROM presencia_personal_actual pp
    JOIN evento_acceso ea ON ea.evento_id = pp.evento_entrada_id
    JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
    JOIN instructor ins ON ins.instructor_id = pp.instructor_id
) p ON p.instalacion_id = i.instalacion_id
GROUP BY i.instalacion_id, i.nombre, i.aforo_maximo;

CREATE VIEW vw_accesos_recientes AS
SELECT ea.evento_id, ea.registrado_en, ea.tipo, ea.resultado, ea.motivo_rechazo,
       pa.nombre AS punto_acceso, i.nombre AS instalacion,
       COALESCE(
           socio_persona.nombres || ' ' || socio_persona."apellidoPaterno" || ' ' || socio_persona."apellidoMaterno",
           personal_persona.nombres || ' ' || personal_persona."apellidoPaterno" || ' ' || personal_persona."apellidoMaterno"
       ) AS socio,
       CASE WHEN ea.credencial_personal_id IS NOT NULL THEN 'PERSONAL' ELSE 'SOCIO' END AS tipo_persona
FROM evento_acceso ea
JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
JOIN instalacion i ON i.instalacion_id = pa.instalacion_id
LEFT JOIN credencial_qr cq ON cq.credencial_id = ea.credencial_id
LEFT JOIN socio s ON s.socio_id = cq.socio_id
LEFT JOIN persona socio_persona ON socio_persona.rut = s.persona_id
LEFT JOIN credencial_personal_qr cpq ON cpq.credencial_personal_id = ea.credencial_personal_id
LEFT JOIN instructor ins ON ins.instructor_id = cpq.instructor_id
LEFT JOIN persona personal_persona ON personal_persona.rut = ins.persona_id;

COMMIT;
