-- FitLife 1.2: imagen opcional para cada sesión de clase.
-- Ejecutar después de 1.1.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE sesion_clase
    ADD COLUMN IF NOT EXISTS imagen_url VARCHAR(500);

COMMIT;
