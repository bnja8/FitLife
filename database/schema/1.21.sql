-- FitLife 1.21: herramientas y asignaciones profesionales por especialidad.
BEGIN;
SET LOCAL search_path TO fitlife, public;

ALTER TABLE sesion_clase
    ADD COLUMN IF NOT EXISTS descripcion_sesion TEXT,
    ADD COLUMN IF NOT EXISTS intensidad VARCHAR(20)
        CHECK (intensidad IS NULL OR intensidad IN ('BAJA', 'MODERADA', 'ALTA')),
    ADD COLUMN IF NOT EXISTS observaciones TEXT;

CREATE TABLE IF NOT EXISTS instructor_socio (
    instructor_id BIGINT NOT NULL REFERENCES instructor(instructor_id) ON DELETE RESTRICT,
    socio_id BIGINT NOT NULL REFERENCES socio(socio_id) ON DELETE RESTRICT,
    asignada_por VARCHAR(30) NOT NULL REFERENCES persona(rut) ON DELETE RESTRICT,
    asignada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (instructor_id, socio_id)
);
CREATE INDEX IF NOT EXISTS idx_instructor_socio_socio
    ON instructor_socio(socio_id, instructor_id);

CREATE TABLE IF NOT EXISTS evaluacion_inicial_personal (
    evaluacion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    objetivo TEXT NOT NULL,
    condicion_inicial TEXT NOT NULL,
    antecedentes TEXT,
    evaluada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS plan_entrenamiento (
    plan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    titulo VARCHAR(120) NOT NULL,
    objetivo TEXT NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    observaciones TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT,
    CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
);

CREATE TABLE IF NOT EXISTS rutina_entrenamiento (
    rutina_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id BIGINT NOT NULL REFERENCES plan_entrenamiento(plan_id) ON DELETE RESTRICT,
    dia VARCHAR(40) NOT NULL,
    orden SMALLINT NOT NULL DEFAULT 1 CHECK (orden > 0),
    UNIQUE (plan_id, dia, orden)
);

CREATE TABLE IF NOT EXISTS ejercicio_entrenamiento (
    ejercicio_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rutina_id BIGINT NOT NULL REFERENCES rutina_entrenamiento(rutina_id) ON DELETE RESTRICT,
    nombre VARCHAR(120) NOT NULL,
    series SMALLINT NOT NULL CHECK (series > 0),
    repeticiones VARCHAR(40) NOT NULL,
    carga_kg NUMERIC(8,2) CHECK (carga_kg IS NULL OR carga_kg >= 0),
    descanso_segundos INTEGER CHECK (descanso_segundos IS NULL OR descanso_segundos >= 0),
    duracion_segundos INTEGER CHECK (duracion_segundos IS NULL OR duracion_segundos >= 0),
    observaciones TEXT
);

CREATE TABLE IF NOT EXISTS sesion_entrenamiento_personal (
    sesion_personal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    plan_id BIGINT REFERENCES plan_entrenamiento(plan_id) ON DELETE RESTRICT,
    realizada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duracion_minutos SMALLINT CHECK (duracion_minutos IS NULL OR duracion_minutos > 0),
    observaciones TEXT,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS progreso_entrenamiento_personal (
    progreso_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    objetivo TEXT NOT NULL,
    progreso SMALLINT NOT NULL CHECK (progreso BETWEEN 0 AND 100),
    observaciones TEXT,
    registrado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS objetivo_coaching (
    objetivo_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    titulo VARCHAR(120) NOT NULL,
    descripcion TEXT,
    fecha_objetivo DATE,
    asistencias_semanales SMALLINT CHECK (asistencias_semanales IS NULL OR asistencias_semanales BETWEEN 1 AND 7),
    estado VARCHAR(20) NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado IN ('PENDIENTE', 'EN_CURSO', 'CUMPLIDO', 'PAUSADO')),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS sesion_coaching (
    sesion_coaching_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    objetivo_id BIGINT REFERENCES objetivo_coaching(objetivo_id) ON DELETE RESTRICT,
    realizada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    compromisos TEXT,
    adherencia SMALLINT CHECK (adherencia IS NULL OR adherencia BETWEEN 0 AND 100),
    observaciones TEXT,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS evaluacion_fisica (
    evaluacion_fisica_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    prueba VARCHAR(120) NOT NULL,
    capacidad VARCHAR(30) NOT NULL
        CHECK (capacidad IN ('RESISTENCIA', 'FUERZA', 'VELOCIDAD', 'FLEXIBILIDAD', 'COMPOSICION', 'OTRA')),
    resultado NUMERIC(12,3) NOT NULL,
    unidad VARCHAR(30) NOT NULL,
    evaluada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observaciones TEXT,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS planificacion_fisica (
    planificacion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instructor_id BIGINT NOT NULL,
    socio_id BIGINT NOT NULL,
    titulo VARCHAR(120) NOT NULL,
    objetivo TEXT NOT NULL,
    etapa VARCHAR(80) NOT NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    volumen_semanal NUMERIC(8,2) CHECK (volumen_semanal IS NULL OR volumen_semanal >= 0),
    intensidad SMALLINT CHECK (intensidad IS NULL OR intensidad BETWEEN 1 AND 10),
    observaciones TEXT,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (instructor_id, socio_id)
        REFERENCES instructor_socio(instructor_id, socio_id) ON DELETE RESTRICT,
    CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
);

CREATE INDEX IF NOT EXISTS idx_plan_entrenamiento_socio
    ON plan_entrenamiento(socio_id, creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_objetivo_coaching_socio
    ON objetivo_coaching(socio_id, creado_en DESC);
CREATE INDEX IF NOT EXISTS idx_evaluacion_fisica_socio
    ON evaluacion_fisica(socio_id, evaluada_en DESC);

COMMIT;
