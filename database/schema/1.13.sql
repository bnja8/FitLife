-- FitLife 1.13: asocia cada membresía a una sede y limita su uso a esa sede.
-- Ejecutar después de 1.12.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE membresia
    ADD COLUMN instalacion_id BIGINT
        REFERENCES instalacion(instalacion_id) ON DELETE RESTRICT;

-- Solo se pueden identificar automáticamente los registros cuyo plan pertenece
-- a una única sede; los históricos ambiguos quedan visibles sin sede asignada.
UPDATE membresia m
SET instalacion_id = sedes.instalacion_id
FROM (
    SELECT plan_id, MIN(instalacion_id) AS instalacion_id
    FROM instalacion_plan
    GROUP BY plan_id
    HAVING COUNT(*) = 1
) sedes
WHERE m.plan_id = sedes.plan_id;

DROP INDEX IF EXISTS uq_membresia_socio_en_curso;
CREATE UNIQUE INDEX uq_membresia_socio_sede_en_curso
    ON membresia(socio_id, instalacion_id)
    WHERE estado IN ('ACTIVA', 'CONGELADA', 'PENDIENTE');

CREATE INDEX idx_membresia_sede_estado
    ON membresia(instalacion_id, estado, fecha_fin DESC);

CREATE OR REPLACE FUNCTION validar_membresia_sede()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
BEGIN
    IF NEW.instalacion_id IS NULL THEN
        RAISE EXCEPTION 'Toda membresía debe estar asociada a una sede.'
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM instalacion_plan ip
        JOIN instalacion i USING (instalacion_id)
        JOIN plan_membresia pm ON pm.plan_id = ip.plan_id AND pm.activo
        WHERE ip.instalacion_id = NEW.instalacion_id
          AND ip.plan_id = NEW.plan_id
          AND i.activa
    ) THEN
        RAISE EXCEPTION 'El plan no está disponible en la sede seleccionada.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validar_membresia_sede
BEFORE INSERT OR UPDATE OF plan_id, instalacion_id ON membresia
FOR EACH ROW
EXECUTE FUNCTION validar_membresia_sede();

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
    pm.incluye_estacionamiento,
    m.instalacion_id,
    i.nombre AS sede
FROM membresia m
JOIN socio s ON s.socio_id = m.socio_id
JOIN persona pe ON pe.rut = s.persona_id
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
        WHERE m.socio_id = p_socio_id
          AND m.instalacion_id = p_instalacion_id
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

CREATE OR REPLACE FUNCTION reservar_clase(
    p_sesion_id BIGINT,
    p_socio_id BIGINT
)
RETURNS TABLE (
    reserva_id BIGINT,
    estado estado_reserva
)
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_sesion sesion_clase%ROWTYPE;
    v_instalacion_id BIGINT;
    v_ocupados INTEGER;
    v_estado estado_reserva;
    v_reserva_id BIGINT;
BEGIN
    SELECT *
      INTO v_sesion
      FROM sesion_clase
     WHERE sesion_id = p_sesion_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La sesión % no existe', p_sesion_id;
    END IF;

    IF v_sesion.estado <> 'PROGRAMADA' OR v_sesion.inicio <= CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'La sesión no admite nuevas reservas';
    END IF;

    SELECT instalacion_id INTO v_instalacion_id
    FROM sala WHERE sala_id = v_sesion.sala_id;

    PERFORM 1
      FROM socio
     WHERE socio_id = p_socio_id
       AND activo = TRUE
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El socio no existe o está inactivo';
    END IF;

    IF NOT socio_tiene_membresia_vigente_en_sede(p_socio_id, v_instalacion_id) THEN
        RAISE EXCEPTION 'El socio no tiene una membresía vigente en la sede de esta clase';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM reserva
         WHERE sesion_id = p_sesion_id
           AND socio_id = p_socio_id
           AND estado <> 'CANCELADA'
    ) THEN
        RAISE EXCEPTION 'El socio ya tiene una reserva o está en lista de espera para esta sesión';
    END IF;

    SELECT COUNT(*)::INTEGER
      INTO v_ocupados
      FROM reserva
     WHERE sesion_id = p_sesion_id
       AND estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE');

    IF v_ocupados < v_sesion.cupos_totales THEN
        v_estado := 'RESERVADA';
    ELSE
        v_estado := 'EN_ESPERA';
    END IF;

    INSERT INTO reserva (sesion_id, socio_id, estado)
    VALUES (p_sesion_id, p_socio_id, v_estado)
    RETURNING reserva.reserva_id INTO v_reserva_id;

    RETURN QUERY SELECT v_reserva_id, v_estado;
END;
$$;

CREATE OR REPLACE FUNCTION registrar_acceso_qr(
    p_token TEXT,
    p_punto_acceso_id BIGINT,
    p_tipo tipo_evento_acceso
)
RETURNS TABLE (
    evento_id BIGINT,
    resultado resultado_acceso,
    motivo_rechazo VARCHAR
)
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_instalacion_id BIGINT;
    v_aforo_maximo INTEGER;
    v_tipo_punto tipo_punto_acceso;
    v_credencial credencial_qr%ROWTYPE;
    v_credencial_id BIGINT;
    v_socio_id BIGINT;
    v_socio_activo BOOLEAN;
    v_aforo_actual INTEGER;
    v_instalacion_presencia BIGINT;
    v_evento_id BIGINT;
    v_motivo VARCHAR(100);
BEGIN
    IF p_tipo IS NULL THEN
        RAISE EXCEPTION 'Debe indicar si el movimiento es ENTRADA o SALIDA';
    END IF;

    SELECT pa.instalacion_id, pa.tipo, i.aforo_maximo
      INTO v_instalacion_id, v_tipo_punto, v_aforo_maximo
      FROM punto_acceso pa
      JOIN instalacion i ON i.instalacion_id = pa.instalacion_id
     WHERE pa.punto_acceso_id = p_punto_acceso_id
       AND pa.activo = TRUE
       AND i.activa = TRUE
     FOR UPDATE OF i;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El punto de acceso no existe o está inactivo';
    END IF;

    IF v_tipo_punto = 'ENTRADA' AND p_tipo = 'SALIDA' THEN
        v_motivo := 'DIRECCION_NO_PERMITIDA';
    ELSIF v_tipo_punto = 'SALIDA' AND p_tipo = 'ENTRADA' THEN
        v_motivo := 'DIRECCION_NO_PERMITIDA';
    END IF;

    IF v_motivo IS NULL THEN
        IF p_token IS NULL OR BTRIM(p_token) = '' THEN
            v_motivo := 'TOKEN_VACIO';
        ELSE
            SELECT *
              INTO v_credencial
              FROM credencial_qr
             WHERE hash_token = public.digest(convert_to(p_token, 'UTF8'), 'sha256');

            IF NOT FOUND THEN
                v_motivo := 'CREDENCIAL_NO_RECONOCIDA';
            ELSE
                v_credencial_id := v_credencial.credencial_id;
                v_socio_id := v_credencial.socio_id;

                IF v_credencial.revocada_en IS NOT NULL THEN
                    v_motivo := 'CREDENCIAL_REVOCADA';
                ELSIF v_credencial.expira_en IS NOT NULL
                      AND v_credencial.expira_en <= CURRENT_TIMESTAMP THEN
                    v_motivo := 'CREDENCIAL_EXPIRADA';
                END IF;
            END IF;
        END IF;
    END IF;

    IF v_motivo IS NULL THEN
        SELECT activo
          INTO v_socio_activo
          FROM socio
         WHERE socio_id = v_socio_id
         FOR UPDATE;

        IF NOT FOUND OR NOT v_socio_activo THEN
            v_motivo := 'SOCIO_INACTIVO';
        ELSIF NOT socio_tiene_membresia_vigente_en_sede(v_socio_id, v_instalacion_id) THEN
            v_motivo := 'MEMBRESIA_NO_VIGENTE_EN_SEDE';
        END IF;
    END IF;

    IF v_motivo IS NULL AND p_tipo = 'ENTRADA' THEN
        IF EXISTS (
            SELECT 1 FROM presencia_actual WHERE socio_id = v_socio_id
        ) THEN
            v_motivo := 'SOCIO_YA_DENTRO';
        ELSE
            SELECT (
                SELECT COUNT(*) FROM presencia_actual pr
                JOIN evento_acceso ea ON ea.evento_id = pr.evento_entrada_id
                JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
                WHERE pa.instalacion_id = v_instalacion_id
            ) + (
                SELECT COUNT(*) FROM presencia_personal_actual pp
                JOIN evento_acceso ea ON ea.evento_id = pp.evento_entrada_id
                JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
                WHERE pa.instalacion_id = v_instalacion_id
            ) INTO v_aforo_actual;

            IF v_aforo_actual >= v_aforo_maximo THEN
                v_motivo := 'AFORO_COMPLETO';
            END IF;
        END IF;
    ELSIF v_motivo IS NULL AND p_tipo = 'SALIDA' THEN
        SELECT pa.instalacion_id
          INTO v_instalacion_presencia
          FROM presencia_actual pr
          JOIN evento_acceso ea ON ea.evento_id = pr.evento_entrada_id
          JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
         WHERE pr.socio_id = v_socio_id
         FOR UPDATE OF pr;

        IF NOT FOUND THEN
            v_motivo := 'SOCIO_SIN_ENTRADA_REGISTRADA';
        ELSIF v_instalacion_presencia <> v_instalacion_id THEN
            v_motivo := 'SALIDA_EN_INSTALACION_DISTINTA';
        END IF;
    END IF;

    IF v_motivo IS NOT NULL THEN
        INSERT INTO evento_acceso (
            punto_acceso_id, credencial_id, tipo, resultado, motivo_rechazo
        ) VALUES (
            p_punto_acceso_id, v_credencial_id, p_tipo, 'RECHAZADO', v_motivo
        )
        RETURNING evento_acceso.evento_id INTO v_evento_id;

        RETURN QUERY
        SELECT v_evento_id, 'RECHAZADO'::resultado_acceso, v_motivo;
        RETURN;
    END IF;

    INSERT INTO evento_acceso (
        punto_acceso_id, credencial_id, tipo, resultado, motivo_rechazo
    ) VALUES (
        p_punto_acceso_id, v_credencial_id, p_tipo, 'AUTORIZADO', NULL
    )
    RETURNING evento_acceso.evento_id INTO v_evento_id;

    IF p_tipo = 'ENTRADA' THEN
        INSERT INTO presencia_actual (socio_id, evento_entrada_id)
        VALUES (v_socio_id, v_evento_id);
    ELSE
        DELETE FROM presencia_actual
         WHERE socio_id = v_socio_id;
    END IF;

    RETURN QUERY
    SELECT v_evento_id, 'AUTORIZADO'::resultado_acceso, NULL::VARCHAR;
END;
$$;

COMMIT;
