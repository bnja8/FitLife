-- FitLife 1.7: suscripciones disponibles por sede.
-- Ejecutar después de 1.6.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

CREATE TABLE instalacion_plan (
    instalacion_id BIGINT NOT NULL
        REFERENCES instalacion(instalacion_id) ON DELETE CASCADE,
    plan_id BIGINT NOT NULL
        REFERENCES plan_membresia(plan_id) ON DELETE CASCADE,
    PRIMARY KEY (instalacion_id, plan_id)
);

CREATE INDEX idx_instalacion_plan_plan
    ON instalacion_plan(plan_id, instalacion_id);

COMMIT;
