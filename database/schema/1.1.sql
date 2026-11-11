-- FitLife 1.1: extensiones para prueba gratis, equipos y seguimiento profesional.
-- Ejecutar una vez sobre la base que ya tiene aplicado 1.0.sql.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE sesion_clase ADD COLUMN IF NOT EXISTS precio NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (precio >= 0);
ALTER TABLE sesion_clase ADD COLUMN IF NOT EXISTS nombre_sesion VARCHAR(120);
UPDATE sesion_clase sc SET nombre_sesion=a.nombre FROM actividad a WHERE a.actividad_id=sc.actividad_id AND sc.nombre_sesion IS NULL;

CREATE OR REPLACE VIEW vw_disponibilidad_clases AS
SELECT sc.sesion_id,a.nombre AS actividad,
       concat_ws(' ',pe.nombres,pe."apellidoPaterno",NULLIF(pe."apellidoMaterno",'-')) AS instructor,
       sa.nombre AS sala,sc.inicio,sc.fin,sc.estado,sc.cupos_totales,
       COUNT(r.reserva_id) FILTER(WHERE r.estado IN('RESERVADA','ASISTIO','AUSENTE'))::INTEGER AS cupos_ocupados,
       GREATEST(sc.cupos_totales-COUNT(r.reserva_id) FILTER(WHERE r.estado IN('RESERVADA','ASISTIO','AUSENTE'))::INTEGER,0) AS cupos_disponibles,
       COUNT(r.reserva_id) FILTER(WHERE r.estado='EN_ESPERA')::INTEGER AS personas_en_espera,
       sc.precio,sc.nombre_sesion AS nombre
FROM sesion_clase sc JOIN actividad a USING(actividad_id)
JOIN instructor ins USING(instructor_id) JOIN persona pe ON pe.rut=ins.persona_id
JOIN sala sa USING(sala_id) LEFT JOIN reserva r USING(sesion_id)
GROUP BY sc.sesion_id,a.nombre,pe.nombres,pe."apellidoPaterno",pe."apellidoMaterno",sa.nombre,
         sc.inicio,sc.fin,sc.estado,sc.cupos_totales,sc.precio,sc.nombre_sesion;

CREATE TABLE IF NOT EXISTS configuracion_gimnasio (
    configuracion_id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (configuracion_id = 1),
    prueba_gratis_activa BOOLEAN NOT NULL DEFAULT TRUE,
    prueba_gratis_dias INTEGER NOT NULL DEFAULT 7 CHECK (prueba_gratis_dias BETWEEN 1 AND 90),
    actualizada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO configuracion_gimnasio (configuracion_id) VALUES (1) ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS prueba_socio (
    persona_id VARCHAR(30) PRIMARY KEY REFERENCES socio(persona_id) ON DELETE RESTRICT,
    membresia_id BIGINT NOT NULL UNIQUE REFERENCES membresia(membresia_id) ON DELETE RESTRICT,
    iniciada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS maquina (
    maquina_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL UNIQUE,
    categoria VARCHAR(80) NOT NULL,
    instalacion_id BIGINT REFERENCES instalacion(instalacion_id) ON DELETE RESTRICT,
    estado VARCHAR(20) NOT NULL DEFAULT 'OPERATIVA' CHECK (estado IN ('OPERATIVA','MANTENCION','FUERA_SERVICIO')),
    observacion TEXT,
    actualizada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS perfil_instructor (
    instructor_id BIGINT PRIMARY KEY REFERENCES instructor(instructor_id) ON DELETE CASCADE,
    tipo VARCHAR(30) NOT NULL CHECK (tipo IN ('MONITOR','PERSONAL_TRAINER','COACH','PREPARADOR_FISICO')),
    especialidad VARCHAR(150),
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS seguimiento_entrenamiento (
    seguimiento_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL REFERENCES instructor(instructor_id) ON DELETE RESTRICT,
    socio_id BIGINT NOT NULL REFERENCES socio(socio_id) ON DELETE RESTRICT,
    tipo VARCHAR(20) NOT NULL CHECK (tipo IN ('PLAN','OBJETIVO','NOTA')),
    titulo VARCHAR(120) NOT NULL,
    detalle TEXT,
    progreso SMALLINT NOT NULL DEFAULT 0 CHECK (progreso BETWEEN 0 AND 100),
    fecha_objetivo DATE,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_seguimiento_socio ON seguimiento_entrenamiento(socio_id, creada_en DESC);

CREATE TABLE IF NOT EXISTS pago_reserva (
    pago_reserva_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reserva_id BIGINT NOT NULL UNIQUE REFERENCES reserva(reserva_id) ON DELETE RESTRICT,
    metodo metodo_pago NOT NULL,
    estado estado_pago NOT NULL DEFAULT 'PENDIENTE',
    monto NUMERIC(12,2) NOT NULL CHECK(monto>0),
    referencia_externa VARCHAR(150) UNIQUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    procesado_en TIMESTAMPTZ,
    CHECK(estado<>'APROBADO' OR procesado_en IS NOT NULL)
);

COMMIT;
