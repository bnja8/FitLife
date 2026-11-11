-- FitLife 1.11: asigna instructores a sedes y requiere que las clases usen
-- una sala e instructor pertenecientes a la misma sede.
-- Ejecutar después de 1.10.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

CREATE TABLE instalacion_instructor (
    instalacion_id BIGINT NOT NULL
        REFERENCES instalacion(instalacion_id) ON DELETE CASCADE,
    instructor_id BIGINT NOT NULL
        REFERENCES instructor(instructor_id) ON DELETE CASCADE,
    PRIMARY KEY (instalacion_id, instructor_id)
);

INSERT INTO instalacion_instructor (instalacion_id, instructor_id)
SELECT DISTINCT sa.instalacion_id, sc.instructor_id
FROM sesion_clase sc
JOIN sala sa USING (sala_id)
ON CONFLICT DO NOTHING;

CREATE INDEX idx_instalacion_instructor_instructor
    ON instalacion_instructor(instructor_id, instalacion_id);

CREATE OR REPLACE FUNCTION validar_sesion_sede()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_instalacion_id BIGINT;
BEGIN
    SELECT instalacion_id INTO v_instalacion_id
    FROM sala
    WHERE sala_id = NEW.sala_id AND activa;

    IF v_instalacion_id IS NULL THEN
        RAISE EXCEPTION 'La sala debe pertenecer a una sede activa.'
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM instalacion_instructor ii
        JOIN instructor ins USING (instructor_id)
        WHERE ii.instalacion_id = v_instalacion_id
          AND ii.instructor_id = NEW.instructor_id
          AND ins.activo
    ) THEN
        RAISE EXCEPTION 'El instructor debe estar asignado a la sede de la sala.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validar_sesion_sede
    BEFORE INSERT OR UPDATE OF instructor_id, sala_id ON sesion_clase
    FOR EACH ROW EXECUTE FUNCTION validar_sesion_sede();

CREATE OR REPLACE FUNCTION validar_retiro_instructor_sede()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM sesion_clase sc
        JOIN sala sa USING (sala_id)
        WHERE sc.instructor_id = OLD.instructor_id
          AND sa.instalacion_id = OLD.instalacion_id
          AND sc.estado IN ('PROGRAMADA', 'EN_CURSO')
          AND (sc.estado = 'EN_CURSO' OR sc.inicio > CURRENT_TIMESTAMP)
    ) THEN
        RAISE EXCEPTION 'No se puede retirar un profesional asignado a una clase activa o futura.'
            USING ERRCODE = '23514';
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_validar_retiro_instructor_sede
    BEFORE DELETE ON instalacion_instructor
    FOR EACH ROW EXECUTE FUNCTION validar_retiro_instructor_sede();

COMMIT;
