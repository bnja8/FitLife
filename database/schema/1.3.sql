-- FitLife 1.3: planes con beneficios, sedes con lockers y membresías pendientes.
-- Ejecutar después de 1.2.sql sobre una base FitLife existente.

BEGIN;
ALTER TYPE fitlife.estado_membresia ADD VALUE IF NOT EXISTS 'PENDIENTE';
COMMIT;

BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE plan_membresia
    ADD COLUMN IF NOT EXISTS incluye_entrenador_personal BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS incluye_lockers BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS otros_beneficios TEXT NOT NULL DEFAULT '';

ALTER TABLE instalacion
    ADD COLUMN IF NOT EXISTS tiene_lockers BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cantidad_lockers INTEGER NOT NULL DEFAULT 0;

ALTER TABLE instalacion
    ADD CONSTRAINT chk_instalacion_lockers
    CHECK (
        cantidad_lockers >= 0
        AND ((tiene_lockers AND cantidad_lockers > 0)
             OR (NOT tiene_lockers AND cantidad_lockers = 0))
    );

ALTER TABLE membresia
    ALTER COLUMN fecha_inicio DROP NOT NULL,
    ALTER COLUMN fecha_fin DROP NOT NULL,
    DROP CONSTRAINT chk_membresia_fechas,
    ADD CONSTRAINT chk_membresia_fechas CHECK (
        (estado = 'PENDIENTE' AND fecha_inicio IS NULL AND fecha_fin IS NULL)
        OR
        (estado <> 'PENDIENTE' AND fecha_inicio IS NOT NULL
         AND fecha_fin IS NOT NULL AND fecha_fin >= fecha_inicio)
    );

DROP INDEX IF EXISTS uq_membresia_socio_en_curso;
CREATE UNIQUE INDEX uq_membresia_socio_en_curso
    ON membresia(socio_id)
    WHERE estado IN ('ACTIVA', 'CONGELADA', 'PENDIENTE');

CREATE OR REPLACE FUNCTION sincronizar_estados_membresia()
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_actualizadas INTEGER;
BEGIN
    UPDATE membresia m
       SET estado = CASE
           WHEN m.fecha_fin < CURRENT_DATE THEN 'VENCIDA'::estado_membresia
           WHEN EXISTS (
               SELECT 1
               FROM congelacion_membresia c
               WHERE c.membresia_id = m.membresia_id
                 AND CURRENT_DATE >= c.fecha_inicio
                 AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
           ) THEN 'CONGELADA'::estado_membresia
           ELSE 'ACTIVA'::estado_membresia
       END
     WHERE m.estado NOT IN ('CANCELADA', 'PENDIENTE')
       AND m.estado IS DISTINCT FROM CASE
           WHEN m.fecha_fin < CURRENT_DATE THEN 'VENCIDA'::estado_membresia
           WHEN EXISTS (
               SELECT 1
               FROM congelacion_membresia c
               WHERE c.membresia_id = m.membresia_id
                 AND CURRENT_DATE >= c.fecha_inicio
                 AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
           ) THEN 'CONGELADA'::estado_membresia
           ELSE 'ACTIVA'::estado_membresia
       END;

    GET DIAGNOSTICS v_actualizadas = ROW_COUNT;
    RETURN v_actualizadas;
END;
$$;

CREATE OR REPLACE FUNCTION validar_activacion_membresia()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_duracion INTEGER;
BEGIN
    IF NEW.estado = 'ACTIVA'
       AND (TG_OP = 'INSERT' OR OLD.estado IS DISTINCT FROM NEW.estado) THEN
        IF NEW.precio_acordado > 0 AND NOT EXISTS (
            SELECT 1
            FROM pago p
            WHERE p.membresia_id = NEW.membresia_id
              AND p.estado = 'APROBADO'
              AND p.procesado_en IS NOT NULL
              AND p.monto = NEW.precio_acordado
        ) THEN
            RAISE EXCEPTION 'No se puede activar una membresía sin un pago aprobado y verificado.'
                USING ERRCODE = 'P0001';
        END IF;

        SELECT duracion_dias INTO v_duracion
        FROM plan_membresia
        WHERE plan_id = NEW.plan_id;

        NEW.fecha_inicio := COALESCE(NEW.fecha_inicio, CURRENT_DATE);
        NEW.fecha_fin := NEW.fecha_inicio + v_duracion - 1;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validar_activacion_membresia ON membresia;
CREATE TRIGGER trg_validar_activacion_membresia
BEFORE INSERT OR UPDATE OF estado ON membresia
FOR EACH ROW
EXECUTE FUNCTION validar_activacion_membresia();

CREATE OR REPLACE VIEW vw_membresias AS
SELECT
    m.membresia_id,
    m.socio_id,
    pe.nombres || ' ' || pe."apellidoPaterno" || ' ' || pe."apellidoMaterno" AS socio,
    pm.nombre AS plan,
    m.estado,
    m.fecha_inicio,
    m.fecha_fin,
    m.precio_acordado,
    CASE
        WHEN m.estado IN ('CANCELADA', 'PENDIENTE') THEN m.estado::TEXT
        WHEN m.fecha_fin < CURRENT_DATE THEN 'VENCIDA'
        WHEN EXISTS (
            SELECT 1
            FROM congelacion_membresia c
            WHERE c.membresia_id = m.membresia_id
              AND CURRENT_DATE >= c.fecha_inicio
              AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
        ) THEN 'CONGELADA'
        ELSE 'ACTIVA'
    END AS estado_calculado,
    pm.incluye_entrenador_personal,
    pm.incluye_lockers,
    pm.otros_beneficios
FROM membresia m
JOIN socio s ON s.socio_id = m.socio_id
JOIN persona pe ON pe.rut = s.persona_id
JOIN plan_membresia pm ON pm.plan_id = m.plan_id;

COMMIT;
