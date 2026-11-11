-- FitLife 1.4: cupos de estacionamiento por sede y beneficio por plan.
-- Ejecutar después de 1.3.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE instalacion
    ADD COLUMN IF NOT EXISTS tiene_estacionamiento BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS cupos_estacionamiento INTEGER NOT NULL DEFAULT 0;

ALTER TABLE instalacion
    ADD CONSTRAINT chk_instalacion_estacionamiento
    CHECK (
        cupos_estacionamiento >= 0
        AND ((tiene_estacionamiento AND cupos_estacionamiento > 0)
             OR (NOT tiene_estacionamiento AND cupos_estacionamiento = 0))
    );

ALTER TABLE plan_membresia
    ADD COLUMN IF NOT EXISTS incluye_estacionamiento BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE credencial_qr cq
SET revocada_en = CURRENT_TIMESTAMP
WHERE cq.revocada_en IS NULL
  AND NOT socio_tiene_membresia_vigente(cq.socio_id);

CREATE OR REPLACE FUNCTION validar_credencial_membresia_vigente()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
BEGIN
    IF NOT socio_tiene_membresia_vigente(NEW.socio_id) THEN
        RAISE EXCEPTION 'Se requiere una membresía vigente para emitir una credencial QR.'
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validar_credencial_membresia_vigente ON credencial_qr;
CREATE TRIGGER trg_validar_credencial_membresia_vigente
BEFORE INSERT ON credencial_qr
FOR EACH ROW
EXECUTE FUNCTION validar_credencial_membresia_vigente();

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
    pm.otros_beneficios,
    pm.incluye_estacionamiento
FROM membresia m
JOIN socio s ON s.socio_id = m.socio_id
JOIN persona pe ON pe.rut = s.persona_id
JOIN plan_membresia pm ON pm.plan_id = m.plan_id;

COMMIT;
