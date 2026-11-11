-- FitLife 1.12: agrega vestidores y duchas como servicios de sede.
-- Ejecutar después de 1.11.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE instalacion
    ADD COLUMN tiene_vestidores BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN cantidad_vestidores INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN tiene_duchas BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN cantidad_duchas INTEGER NOT NULL DEFAULT 0,
    ADD CONSTRAINT chk_instalacion_vestidores_cantidad
        CHECK (
            cantidad_vestidores >= 0
            AND ((tiene_vestidores AND cantidad_vestidores > 0)
                 OR (NOT tiene_vestidores AND cantidad_vestidores = 0))
        ),
    ADD CONSTRAINT chk_instalacion_duchas_cantidad
        CHECK (
            cantidad_duchas >= 0
            AND ((tiene_duchas AND cantidad_duchas > 0)
                 OR (NOT tiene_duchas AND cantidad_duchas = 0))
        );

COMMIT;
