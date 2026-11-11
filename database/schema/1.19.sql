-- FitLife 1.19: asignación de una sede por cuenta de recepción.
BEGIN;
SET LOCAL search_path TO fitlife, public;

CREATE TABLE recepcionista_sede (
    rut VARCHAR(12) PRIMARY KEY
        REFERENCES usuario(rut) ON DELETE CASCADE,
    instalacion_id BIGINT NOT NULL
        REFERENCES instalacion(instalacion_id) ON DELETE RESTRICT
);

CREATE INDEX idx_recepcionista_sede_instalacion
    ON recepcionista_sede (instalacion_id);

COMMIT;
