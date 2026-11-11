-- FitLife 1.6: horarios y ubicación de las sedes.
-- Ejecutar después de 1.5.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE instalacion
    ADD COLUMN horario_lunes_viernes VARCHAR(100),
    ADD COLUMN horario_sabados_dom_festivos VARCHAR(100),
    ADD COLUMN caracteristicas TEXT NOT NULL DEFAULT '',
    ADD COLUMN latitud NUMERIC(9, 6),
    ADD COLUMN longitud NUMERIC(9, 6),
    ADD CONSTRAINT chk_instalacion_coordenadas_pares
        CHECK (num_nonnulls(latitud, longitud) IN (0, 2)),
    ADD CONSTRAINT chk_instalacion_coordenadas_rango
        CHECK (
            (latitud IS NULL OR latitud BETWEEN -90 AND 90)
            AND (longitud IS NULL OR longitud BETWEEN -180 AND 180)
        );

COMMIT;
