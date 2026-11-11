-- FitLife 1.18: asociación de máquinas a salas de su misma sede.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE sala
    ADD CONSTRAINT uq_sala_id_instalacion UNIQUE (sala_id, instalacion_id);

ALTER TABLE maquina
    ADD COLUMN sala_id BIGINT,
    ADD CONSTRAINT fk_maquina_sala_instalacion
        FOREIGN KEY (sala_id, instalacion_id)
        REFERENCES sala (sala_id, instalacion_id)
        ON DELETE RESTRICT;

CREATE INDEX idx_maquina_sala_instalacion
    ON maquina (sala_id, instalacion_id);

COMMIT;
