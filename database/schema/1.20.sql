-- FitLife 1.20: clasifica puntos de acceso para estacionamientos por sede.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE punto_acceso
    ADD COLUMN uso VARCHAR(20) NOT NULL DEFAULT 'GENERAL',
    ADD CONSTRAINT chk_punto_acceso_uso
        CHECK (uso IN ('GENERAL', 'ESTACIONAMIENTO'));

COMMIT;
