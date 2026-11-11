-- FitLife 1.10: clasifica los planes y guarda la región y ciudad de cada sede.
-- Ejecutar después de 1.9.sql sobre una base FitLife existente.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE plan_membresia
    ADD COLUMN tipo VARCHAR(12) NOT NULL DEFAULT 'PLAN'
        CHECK (tipo IN ('PLAN', 'MEMBRESIA'));

ALTER TABLE instalacion
    ADD COLUMN region VARCHAR(100),
    ADD COLUMN ciudad VARCHAR(100),
    ADD CONSTRAINT chk_instalacion_region_ciudad_pares
        CHECK (num_nonnulls(region, ciudad) IN (0, 2)),
    ADD CONSTRAINT chk_instalacion_region_valida
        CHECK (
            region IS NULL OR region IN (
                'Arica y Parinacota',
                'Tarapacá',
                'Antofagasta',
                'Atacama',
                'Coquimbo',
                'Valparaíso',
                'Metropolitana de Santiago',
                'Libertador General Bernardo O''Higgins',
                'Maule',
                'Ñuble',
                'Biobío',
                'La Araucanía',
                'Los Ríos',
                'Los Lagos',
                'Aysén del General Carlos Ibáñez del Campo',
                'Magallanes y de la Antártica Chilena'
            )
        ),
    ADD CONSTRAINT chk_instalacion_ciudad_no_vacia
        CHECK (ciudad IS NULL OR BTRIM(ciudad) <> '');

COMMIT;
