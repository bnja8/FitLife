-- FitLife 1.8: imágenes públicas para las tarjetas de sedes.
-- Ejecutar después de 1.7.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE instalacion
    ADD COLUMN imagen_url VARCHAR(500);

COMMIT;
