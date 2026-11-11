-- FitLife 1.15: nombra las relaciones con personas como rut.
BEGIN;
SET LOCAL search_path TO fitlife, public;

DO $$
DECLARE
    child_table TEXT;
    has_persona_id BOOLEAN;
    has_rut BOOLEAN;
    child_tables TEXT[] := ARRAY['usuario', 'usuario_rol', 'socio', 'instructor', 'prueba_socio'];
BEGIN
    FOREACH child_table IN ARRAY child_tables LOOP
        IF to_regclass(format('fitlife.%I', child_table)) IS NULL THEN
            CONTINUE;
        END IF;

        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'fitlife' AND table_name = child_table
              AND column_name = 'persona_id'
        ) INTO has_persona_id;
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'fitlife' AND table_name = child_table
              AND column_name = 'rut'
        ) INTO has_rut;

        IF has_persona_id AND has_rut THEN
            RAISE EXCEPTION 'La tabla % contiene persona_id y rut; revisa su esquema antes de migrar.', child_table;
        ELSIF has_persona_id THEN
            EXECUTE format('ALTER TABLE %I RENAME COLUMN persona_id TO rut', child_table);
        ELSIF NOT has_rut THEN
            RAISE EXCEPTION 'La tabla % no contiene la columna de relación persona_id ni rut.', child_table;
        END IF;
    END LOOP;
END
$$;

ALTER TABLE socio ALTER COLUMN rut SET NOT NULL;
ALTER TABLE instructor ALTER COLUMN rut SET NOT NULL;

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
            WHERE ur.rut = i.rut
              AND r.codigo = 'INSTRUCTOR'
        )
          INTO v_personal_activo
          FROM instructor i
          JOIN usuario u USING (rut)
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

COMMIT;
