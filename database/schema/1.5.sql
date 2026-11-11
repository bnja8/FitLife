-- FitLife 1.5: credenciales QR y control de acceso para el equipo profesional.
-- Ejecutar después de 1.4.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

CREATE TABLE IF NOT EXISTS credencial_personal_qr (
    credencial_personal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL
        REFERENCES instructor(instructor_id) ON DELETE RESTRICT,
    hash_token BYTEA NOT NULL UNIQUE,
    emitida_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en TIMESTAMPTZ,
    revocada_en TIMESTAMPTZ,
    CONSTRAINT chk_personal_qr_hash CHECK (OCTET_LENGTH(hash_token) = 32),
    CONSTRAINT chk_personal_qr_expiracion
        CHECK (expira_en IS NULL OR expira_en > emitida_en)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_personal_qr_instructor_no_revocada
    ON credencial_personal_qr(instructor_id)
    WHERE revocada_en IS NULL;

ALTER TABLE evento_acceso
    ADD COLUMN IF NOT EXISTS credencial_personal_id BIGINT
        REFERENCES credencial_personal_qr(credencial_personal_id) ON DELETE RESTRICT;

ALTER TABLE evento_acceso
    DROP CONSTRAINT IF EXISTS chk_resultado_acceso;

ALTER TABLE evento_acceso
    ADD CONSTRAINT chk_resultado_acceso CHECK (
        (resultado = 'AUTORIZADO'
            AND num_nonnulls(credencial_id, credencial_personal_id) = 1
            AND motivo_rechazo IS NULL)
        OR
        (resultado = 'RECHAZADO'
            AND num_nonnulls(credencial_id, credencial_personal_id) <= 1
            AND motivo_rechazo IS NOT NULL)
    );

CREATE INDEX IF NOT EXISTS idx_evento_personal_credencial_fecha
    ON evento_acceso(credencial_personal_id, registrado_en DESC)
    WHERE credencial_personal_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS presencia_personal_actual (
    instructor_id BIGINT PRIMARY KEY
        REFERENCES instructor(instructor_id) ON DELETE RESTRICT,
    evento_entrada_id BIGINT NOT NULL UNIQUE
        REFERENCES evento_acceso(evento_id) ON DELETE RESTRICT
);

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
        ELSIF NOT socio_tiene_membresia_vigente(v_socio_id) THEN
            v_motivo := 'MEMBRESIA_NO_VIGENTE';
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

CREATE OR REPLACE FUNCTION registrar_acceso_personal_qr(
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
    v_credencial credencial_personal_qr%ROWTYPE;
    v_instructor_id BIGINT;
    v_personal_activo BOOLEAN;
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
              FROM credencial_personal_qr
             WHERE hash_token = public.digest(convert_to(p_token, 'UTF8'), 'sha256');

            IF NOT FOUND THEN
                v_motivo := 'CREDENCIAL_NO_RECONOCIDA';
            ELSE
                v_instructor_id := v_credencial.instructor_id;
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
        SELECT i.activo AND u.activo AND EXISTS (
            SELECT 1
            FROM usuario_rol ur
            JOIN rol r USING (rol_id)
            WHERE ur.persona_id = i.persona_id
              AND r.codigo = 'INSTRUCTOR'
        )
          INTO v_personal_activo
          FROM instructor i
          JOIN usuario u USING (persona_id)
         WHERE i.instructor_id = v_instructor_id
         FOR UPDATE OF i, u;

        IF NOT FOUND OR NOT v_personal_activo THEN
            v_motivo := 'PERSONAL_INACTIVO';
        END IF;
    END IF;

    IF v_motivo IS NULL AND p_tipo = 'ENTRADA' THEN
        IF EXISTS (
            SELECT 1 FROM presencia_personal_actual
            WHERE instructor_id = v_instructor_id
        ) THEN
            v_motivo := 'PERSONAL_YA_DENTRO';
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
          FROM presencia_personal_actual pp
          JOIN evento_acceso ea ON ea.evento_id = pp.evento_entrada_id
          JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
         WHERE pp.instructor_id = v_instructor_id
         FOR UPDATE OF pp;

        IF NOT FOUND THEN
            v_motivo := 'PERSONAL_SIN_ENTRADA_REGISTRADA';
        ELSIF v_instalacion_presencia <> v_instalacion_id THEN
            v_motivo := 'SALIDA_EN_INSTALACION_DISTINTA';
        END IF;
    END IF;

    IF v_motivo IS NOT NULL THEN
        INSERT INTO evento_acceso (
            punto_acceso_id, credencial_personal_id, tipo, resultado, motivo_rechazo
        ) VALUES (
            p_punto_acceso_id, v_credencial.credencial_personal_id,
            p_tipo, 'RECHAZADO', v_motivo
        )
        RETURNING evento_acceso.evento_id INTO v_evento_id;

        RETURN QUERY
        SELECT v_evento_id, 'RECHAZADO'::resultado_acceso, v_motivo;
        RETURN;
    END IF;

    INSERT INTO evento_acceso (
        punto_acceso_id, credencial_personal_id, tipo, resultado, motivo_rechazo
    ) VALUES (
        p_punto_acceso_id, v_credencial.credencial_personal_id,
        p_tipo, 'AUTORIZADO', NULL
    )
    RETURNING evento_acceso.evento_id INTO v_evento_id;

    IF p_tipo = 'ENTRADA' THEN
        INSERT INTO presencia_personal_actual (instructor_id, evento_entrada_id)
        VALUES (v_instructor_id, v_evento_id);
    ELSE
        DELETE FROM presencia_personal_actual
         WHERE instructor_id = v_instructor_id;
    END IF;

    RETURN QUERY
    SELECT v_evento_id, 'AUTORIZADO'::resultado_acceso, NULL::VARCHAR;
END;
$$;

CREATE OR REPLACE VIEW vw_aforo_actual AS
SELECT
    i.instalacion_id,
    i.nombre AS instalacion,
    i.aforo_maximo,
    COUNT(p.persona_id)::INTEGER AS personas_presentes,
    GREATEST(
        i.aforo_maximo - COUNT(p.persona_id)::INTEGER,
        0
    ) AS cupos_disponibles,
    ROUND(
        (COUNT(p.persona_id)::NUMERIC / NULLIF(i.aforo_maximo, 0)) * 100,
        2
    ) AS porcentaje_ocupacion
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

CREATE OR REPLACE VIEW vw_accesos_recientes AS
SELECT
    ea.evento_id,
    ea.registrado_en,
    ea.tipo,
    ea.resultado,
    ea.motivo_rechazo,
    pa.nombre AS punto_acceso,
    i.nombre AS instalacion,
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
