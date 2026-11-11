-- FitLife 1.17: pruebas gratuitas por sede y membresías con acceso global.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE plan_membresia
    ADD COLUMN acceso_todas_sedes BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN es_prueba_gratuita BOOLEAN NOT NULL DEFAULT FALSE,
    ADD CONSTRAINT chk_plan_prueba_gratuita_gratis
        CHECK (NOT es_prueba_gratuita OR precio_referencia = 0),
    ADD CONSTRAINT chk_plan_prueba_no_global
        CHECK (NOT es_prueba_gratuita OR NOT acceso_todas_sedes),
    ADD CONSTRAINT chk_plan_acceso_global_membresia
        CHECK (NOT acceso_todas_sedes OR tipo = 'MEMBRESIA');

CREATE OR REPLACE FUNCTION validar_membresia_sede()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_acceso_global BOOLEAN;
BEGIN
    IF NEW.instalacion_id IS NULL THEN
        RAISE EXCEPTION 'Toda membresía debe estar asociada a una sede.'
            USING ERRCODE = '23514';
    END IF;

    PERFORM 1
      FROM socio
     WHERE socio_id = NEW.socio_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El socio de la membresía no existe.'
            USING ERRCODE = '23503';
    END IF;

    SELECT acceso_todas_sedes
      INTO v_acceso_global
      FROM plan_membresia
     WHERE plan_id = NEW.plan_id
       AND activo;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El plan de la membresía no existe o está inactivo.'
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM instalacion
         WHERE instalacion_id = NEW.instalacion_id
           AND activa
    ) THEN
        RAISE EXCEPTION 'La sede de la membresía no existe o está inactiva.'
            USING ERRCODE = '23514';
    END IF;

    IF NOT v_acceso_global AND NOT EXISTS (
        SELECT 1
          FROM instalacion_plan ip
          JOIN instalacion i USING (instalacion_id)
         WHERE ip.instalacion_id = NEW.instalacion_id
           AND ip.plan_id = NEW.plan_id
           AND i.activa
    ) THEN
        RAISE EXCEPTION 'El plan no está disponible en la sede seleccionada.'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.estado IN ('ACTIVA', 'CONGELADA', 'PENDIENTE') AND EXISTS (
        SELECT 1
          FROM membresia m
          JOIN plan_membresia pm USING (plan_id)
         WHERE m.socio_id = NEW.socio_id
           AND m.membresia_id IS DISTINCT FROM NEW.membresia_id
           AND m.estado IN ('ACTIVA', 'CONGELADA', 'PENDIENTE')
           AND (
               m.estado = 'PENDIENTE'
               OR m.fecha_fin IS NULL
               OR m.fecha_fin >= CURRENT_DATE
           )
           AND (v_acceso_global OR pm.acceso_todas_sedes)
    ) THEN
        RAISE EXCEPTION 'No se puede combinar una membresía global con otra membresía vigente.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_validar_membresia_sede ON membresia;
CREATE TRIGGER trg_validar_membresia_sede
BEFORE INSERT OR UPDATE OF socio_id, plan_id, instalacion_id, estado ON membresia
FOR EACH ROW
EXECUTE FUNCTION validar_membresia_sede();

CREATE OR REPLACE VIEW vw_membresias AS
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
       pm.incluye_estacionamiento, m.instalacion_id, i.nombre AS sede,
       pm.acceso_todas_sedes, pm.es_prueba_gratuita
FROM membresia m
JOIN socio s ON s.socio_id = m.socio_id
JOIN persona pe ON pe.rut = s.rut
JOIN plan_membresia pm ON pm.plan_id = m.plan_id
LEFT JOIN instalacion i ON i.instalacion_id = m.instalacion_id;

CREATE OR REPLACE FUNCTION socio_tiene_membresia_vigente_en_sede(
    p_socio_id BIGINT,
    p_instalacion_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
SET search_path = fitlife, public
AS $$
    SELECT EXISTS (
        SELECT 1
          FROM membresia m
          JOIN plan_membresia pm USING (plan_id)
         WHERE m.socio_id = p_socio_id
           AND (m.instalacion_id = p_instalacion_id OR pm.acceso_todas_sedes)
           AND m.estado IN ('ACTIVA', 'CONGELADA')
           AND CURRENT_DATE BETWEEN m.fecha_inicio AND m.fecha_fin
           AND NOT EXISTS (
               SELECT 1
                 FROM congelacion_membresia c
                WHERE c.membresia_id = m.membresia_id
                  AND CURRENT_DATE >= c.fecha_inicio
                  AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
           )
    );
$$;

COMMIT;
