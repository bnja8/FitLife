/* ============================================================================
   FITLIFE - PLATAFORMA DE CONTROL DE ASISTENCIA Y RESERVA DE CLASES
   Motor: PostgreSQL 14+
   Normalización: diseño relacional orientado a 3FN

   INSTRUCCIONES:
   1) Ejecutar en una base de datos vacía (por ejemplo, fitlife_db).
   2) El usuario de PostgreSQL debe poder crear extensiones y esquemas.
   3) Este script no elimina datos ni esquemas existentes. Está pensado para
      una instalación inicial; no es un script de migración/reinstalación.
   4) El backend debe usar las funciones de negocio incluidas para registrar
      accesos y reservas; no debe modificar directamente las tablas operativas.

   EXTENSIONES:
   - pgcrypto: SHA-256 para almacenar hashes de credenciales QR.
   - btree_gist: restricciones de exclusión para evitar solapamientos.

   REGLA DE CONGELACIÓN:
   La congelación suspende el acceso durante el intervalo registrado, pero
   este diseño NO extiende automáticamente la fecha_fin de la membresía.
   Esa política puede modificarse si FitLife decide compensar los días congelados.
   ============================================================================ */

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;

CREATE SCHEMA IF NOT EXISTS fitlife;
SET LOCAL search_path TO fitlife, public;

-- ---------------------------------------------------------------------------
-- 1. TIPOS ENUMERADOS
-- ---------------------------------------------------------------------------

CREATE TYPE estado_membresia AS ENUM (
    'ACTIVA',
    'VENCIDA',
    'CONGELADA',
    'CANCELADA'
);

CREATE TYPE estado_pago AS ENUM (
    'PENDIENTE',
    'APROBADO',
    'RECHAZADO',
    'REEMBOLSADO'
);

CREATE TYPE metodo_pago AS ENUM (
    'EFECTIVO',
    'DEBITO',
    'CREDITO',
    'TRANSFERENCIA',
    'OTRO'
);

CREATE TYPE tipo_punto_acceso AS ENUM (
    'ENTRADA',
    'SALIDA',
    'BIDIRECCIONAL'
);

CREATE TYPE tipo_evento_acceso AS ENUM (
    'ENTRADA',
    'SALIDA'
);

CREATE TYPE resultado_acceso AS ENUM (
    'AUTORIZADO',
    'RECHAZADO'
);

CREATE TYPE estado_sesion AS ENUM (
    'PROGRAMADA',
    'EN_CURSO',
    'FINALIZADA',
    'CANCELADA'
);

CREATE TYPE estado_reserva AS ENUM (
    'RESERVADA',
    'EN_ESPERA',
    'CANCELADA',
    'ASISTIO',
    'AUSENTE'
);

-- ---------------------------------------------------------------------------
-- 2. PERSONAS, USUARIOS, ROLES, SOCIOS E INSTRUCTORES
-- ---------------------------------------------------------------------------

CREATE TABLE persona (
    rut VARCHAR(30) PRIMARY KEY,
    nombres VARCHAR(100) NOT NULL,
    "apellidoPaterno" VARCHAR(100) NOT NULL,
    "apellidoMaterno" VARCHAR(100) NOT NULL,
    correo VARCHAR(254) NOT NULL,
    telefono VARCHAR(30),
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- La unicidad del correo no distingue mayúsculas/minúsculas.
CREATE UNIQUE INDEX uq_persona_correo_normalizado
    ON persona (LOWER(correo));

CREATE TABLE usuario (
    persona_id VARCHAR(30) PRIMARY KEY
        REFERENCES persona(rut) ON DELETE RESTRICT,
    hash_contrasena TEXT NOT NULL,
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE rol (
    rol_id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo VARCHAR(30) NOT NULL UNIQUE,
    descripcion VARCHAR(150)
);

CREATE TABLE usuario_rol (
    persona_id VARCHAR(30) NOT NULL
        REFERENCES usuario(persona_id) ON DELETE CASCADE,
    rol_id SMALLINT NOT NULL
        REFERENCES rol(rol_id) ON DELETE RESTRICT,
    PRIMARY KEY (persona_id, rol_id)
);

CREATE TABLE socio (
    socio_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    persona_id VARCHAR(30) NOT NULL UNIQUE
        REFERENCES persona(rut) ON DELETE RESTRICT,
    fecha_alta DATE NOT NULL DEFAULT CURRENT_DATE,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE instructor (
    instructor_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    persona_id VARCHAR(30) NOT NULL UNIQUE
        REFERENCES persona(rut) ON DELETE RESTRICT,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- ---------------------------------------------------------------------------
-- 3. PLANES, MEMBRESÍAS, CONGELACIONES Y PAGOS
-- ---------------------------------------------------------------------------

CREATE TABLE plan_membresia (
    plan_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL UNIQUE,
    descripcion TEXT,
    duracion_dias INTEGER NOT NULL CHECK (duracion_dias > 0),
    precio_referencia NUMERIC(12,2) NOT NULL CHECK (precio_referencia >= 0),
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE membresia (
    membresia_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    socio_id BIGINT NOT NULL
        REFERENCES socio(socio_id) ON DELETE RESTRICT,
    plan_id BIGINT NOT NULL
        REFERENCES plan_membresia(plan_id) ON DELETE RESTRICT,
    estado estado_membresia NOT NULL DEFAULT 'ACTIVA',
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    precio_acordado NUMERIC(12,2) NOT NULL CHECK (precio_acordado >= 0),
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_membresia_fechas CHECK (fecha_fin >= fecha_inicio)
);

-- Política del modelo: un socio puede tener como máximo una membresía en curso.
CREATE UNIQUE INDEX uq_membresia_socio_en_curso
    ON membresia(socio_id)
    WHERE estado IN ('ACTIVA', 'CONGELADA');

CREATE INDEX idx_membresia_socio_estado_fin
    ON membresia(socio_id, estado, fecha_fin DESC);

CREATE TABLE congelacion_membresia (
    congelacion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    membresia_id BIGINT NOT NULL
        REFERENCES membresia(membresia_id) ON DELETE RESTRICT,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    motivo TEXT,
    registrada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_congelacion_fechas
        CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio),
    CONSTRAINT ex_congelaciones_no_superpuestas
        EXCLUDE USING gist (
            membresia_id WITH =,
            daterange(
                fecha_inicio,
                CASE
                    WHEN fecha_fin IS NULL THEN 'infinity'::DATE
                    ELSE fecha_fin + 1
                END,
                '[)'
            ) WITH &&
        )
);

CREATE UNIQUE INDEX uq_congelacion_abierta
    ON congelacion_membresia(membresia_id)
    WHERE fecha_fin IS NULL;

CREATE INDEX idx_congelacion_membresia_fechas
    ON congelacion_membresia(membresia_id, fecha_inicio, fecha_fin);

CREATE TABLE pago (
    pago_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    membresia_id BIGINT NOT NULL
        REFERENCES membresia(membresia_id) ON DELETE RESTRICT,
    metodo metodo_pago NOT NULL,
    estado estado_pago NOT NULL DEFAULT 'PENDIENTE',
    monto NUMERIC(12,2) NOT NULL CHECK (monto > 0),
    referencia_externa VARCHAR(150) UNIQUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    procesado_en TIMESTAMPTZ,
    CONSTRAINT chk_pago_aprobado
        CHECK (estado <> 'APROBADO' OR procesado_en IS NOT NULL)
);

CREATE INDEX idx_pago_membresia_fecha
    ON pago(membresia_id, creado_en DESC);

-- ---------------------------------------------------------------------------
-- 4. INSTALACIONES, PUNTOS DE ACCESO, CREDENCIALES QR Y AFORO
-- ---------------------------------------------------------------------------

CREATE TABLE instalacion (
    instalacion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    direccion VARCHAR(200),
    aforo_maximo INTEGER NOT NULL CHECK (aforo_maximo > 0),
    activa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE punto_acceso (
    punto_acceso_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instalacion_id BIGINT NOT NULL
        REFERENCES instalacion(instalacion_id) ON DELETE RESTRICT,
    nombre VARCHAR(100) NOT NULL,
    tipo tipo_punto_acceso NOT NULL DEFAULT 'BIDIRECCIONAL',
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (instalacion_id, nombre)
);

CREATE TABLE credencial_qr (
    credencial_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    socio_id BIGINT NOT NULL
        REFERENCES socio(socio_id) ON DELETE RESTRICT,
    hash_token BYTEA NOT NULL UNIQUE,
    emitida_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expira_en TIMESTAMPTZ,
    revocada_en TIMESTAMPTZ,
    CONSTRAINT chk_qr_hash CHECK (OCTET_LENGTH(hash_token) = 32),
    CONSTRAINT chk_qr_expiracion
        CHECK (expira_en IS NULL OR expira_en > emitida_en)
);

-- Una credencial no revocada por socio. Para emitir otra, revocar primero la anterior.
CREATE UNIQUE INDEX uq_qr_socio_no_revocado
    ON credencial_qr(socio_id)
    WHERE revocada_en IS NULL;

CREATE TABLE evento_acceso (
    evento_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    punto_acceso_id BIGINT NOT NULL
        REFERENCES punto_acceso(punto_acceso_id) ON DELETE RESTRICT,
    credencial_id BIGINT
        REFERENCES credencial_qr(credencial_id) ON DELETE RESTRICT,
    tipo tipo_evento_acceso NOT NULL,
    resultado resultado_acceso NOT NULL,
    motivo_rechazo VARCHAR(100),
    registrado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_resultado_acceso CHECK (
        (resultado = 'AUTORIZADO'
            AND credencial_id IS NOT NULL
            AND motivo_rechazo IS NULL)
        OR
        (resultado = 'RECHAZADO'
            AND motivo_rechazo IS NOT NULL)
    )
);

CREATE INDEX idx_evento_punto_fecha
    ON evento_acceso(punto_acceso_id, registrado_en DESC);

CREATE INDEX idx_evento_credencial_fecha
    ON evento_acceso(credencial_id, registrado_en DESC)
    WHERE credencial_id IS NOT NULL;

-- Una persona puede tener una única presencia abierta en FitLife.
-- El punto de acceso/instalación se obtiene del evento de entrada relacionado.
CREATE TABLE presencia_actual (
    socio_id BIGINT PRIMARY KEY
        REFERENCES socio(socio_id) ON DELETE RESTRICT,
    evento_entrada_id BIGINT NOT NULL UNIQUE
        REFERENCES evento_acceso(evento_id) ON DELETE RESTRICT
);

-- ---------------------------------------------------------------------------
-- 5. ACTIVIDADES, SALAS, SESIONES Y RESERVAS
-- ---------------------------------------------------------------------------

CREATE TABLE actividad (
    actividad_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE,
    descripcion TEXT,
    activa BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE sala (
    sala_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    instalacion_id BIGINT NOT NULL
        REFERENCES instalacion(instalacion_id) ON DELETE RESTRICT,
    nombre VARCHAR(100) NOT NULL,
    capacidad INTEGER NOT NULL CHECK (capacidad > 0),
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (instalacion_id, nombre)
);

CREATE TABLE sesion_clase (
    sesion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actividad_id BIGINT NOT NULL
        REFERENCES actividad(actividad_id) ON DELETE RESTRICT,
    instructor_id BIGINT NOT NULL
        REFERENCES instructor(instructor_id) ON DELETE RESTRICT,
    sala_id BIGINT NOT NULL
        REFERENCES sala(sala_id) ON DELETE RESTRICT,
    inicio TIMESTAMPTZ NOT NULL,
    fin TIMESTAMPTZ NOT NULL,
    cupos_totales INTEGER NOT NULL CHECK (cupos_totales > 0),
    estado estado_sesion NOT NULL DEFAULT 'PROGRAMADA',
    CONSTRAINT chk_sesion_horario CHECK (fin > inicio),
    -- No permite dos clases simultáneas en una misma sala.
    CONSTRAINT ex_sesion_sala_horario
        EXCLUDE USING gist (
            sala_id WITH =,
            tstzrange(inicio, fin, '[)') WITH &&
        ) WHERE (estado IN ('PROGRAMADA', 'EN_CURSO')),
    -- Un instructor tampoco puede impartir dos clases a la vez.
    CONSTRAINT ex_sesion_instructor_horario
        EXCLUDE USING gist (
            instructor_id WITH =,
            tstzrange(inicio, fin, '[)') WITH &&
        ) WHERE (estado IN ('PROGRAMADA', 'EN_CURSO'))
);

CREATE INDEX idx_sesion_inicio_estado
    ON sesion_clase(inicio, estado);

CREATE INDEX idx_sesion_actividad_inicio
    ON sesion_clase(actividad_id, inicio);

CREATE TABLE reserva (
    reserva_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sesion_id BIGINT NOT NULL
        REFERENCES sesion_clase(sesion_id) ON DELETE RESTRICT,
    socio_id BIGINT NOT NULL
        REFERENCES socio(socio_id) ON DELETE RESTRICT,
    estado estado_reserva NOT NULL,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cancelada_en TIMESTAMPTZ,
    asistio_en TIMESTAMPTZ,
    CONSTRAINT chk_reserva_fechas CHECK (
        (estado = 'CANCELADA'
            AND cancelada_en IS NOT NULL
            AND asistio_en IS NULL)
        OR
        (estado = 'ASISTIO'
            AND cancelada_en IS NULL
            AND asistio_en IS NOT NULL)
        OR
        (estado NOT IN ('CANCELADA', 'ASISTIO')
            AND cancelada_en IS NULL
            AND asistio_en IS NULL)
    )
);

-- Evita reservas activas duplicadas para un mismo socio y sesión.
CREATE UNIQUE INDEX uq_reserva_socio_sesion_no_cancelada
    ON reserva(sesion_id, socio_id)
    WHERE estado <> 'CANCELADA';

CREATE INDEX idx_reserva_sesion_estado_fecha
    ON reserva(sesion_id, estado, creada_en);

CREATE INDEX idx_reserva_socio_fecha
    ON reserva(socio_id, creada_en DESC);

-- ---------------------------------------------------------------------------
-- 6. FUNCIONES AUXILIARES Y REGLAS DE MEMBRESÍA
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION socio_tiene_membresia_vigente(p_socio_id BIGINT)
RETURNS BOOLEAN
LANGUAGE SQL
STABLE
SET search_path = fitlife, public
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM membresia m
        WHERE m.socio_id = p_socio_id
          AND m.estado IN ('ACTIVA', 'CONGELADA')
          AND CURRENT_DATE BETWEEN m.fecha_inicio AND m.fecha_fin
          AND NOT EXISTS (
              SELECT 1
              FROM congelacion_membresia c
              WHERE c.membresia_id = m.membresia_id
                AND CURRENT_DATE >= c.fecha_inicio
                AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
          )
    );
$$;

CREATE OR REPLACE FUNCTION sincronizar_estados_membresia()
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_actualizadas INTEGER;
BEGIN
    UPDATE membresia m
       SET estado = CASE
           WHEN m.fecha_fin < CURRENT_DATE THEN 'VENCIDA'::estado_membresia
           WHEN EXISTS (
               SELECT 1
               FROM congelacion_membresia c
               WHERE c.membresia_id = m.membresia_id
                 AND CURRENT_DATE >= c.fecha_inicio
                 AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
           ) THEN 'CONGELADA'::estado_membresia
           ELSE 'ACTIVA'::estado_membresia
       END
     WHERE m.estado <> 'CANCELADA'
       AND m.estado IS DISTINCT FROM CASE
           WHEN m.fecha_fin < CURRENT_DATE THEN 'VENCIDA'::estado_membresia
           WHEN EXISTS (
               SELECT 1
               FROM congelacion_membresia c
               WHERE c.membresia_id = m.membresia_id
                 AND CURRENT_DATE >= c.fecha_inicio
                 AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
           ) THEN 'CONGELADA'::estado_membresia
           ELSE 'ACTIVA'::estado_membresia
       END;

    GET DIAGNOSTICS v_actualizadas = ROW_COUNT;
    RETURN v_actualizadas;
END;
$$;

CREATE OR REPLACE FUNCTION registrar_congelacion(
    p_membresia_id BIGINT,
    p_fecha_inicio DATE,
    p_fecha_fin DATE DEFAULT NULL,
    p_motivo TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_membresia membresia%ROWTYPE;
    v_congelacion_id BIGINT;
BEGIN
    SELECT *
      INTO v_membresia
      FROM membresia
     WHERE membresia_id = p_membresia_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La membresía % no existe', p_membresia_id;
    END IF;

    IF v_membresia.estado = 'CANCELADA' THEN
        RAISE EXCEPTION 'No se puede congelar una membresía cancelada';
    END IF;

    IF p_fecha_inicio IS NULL OR p_fecha_inicio < CURRENT_DATE THEN
        RAISE EXCEPTION 'La fecha de inicio de congelación no puede estar en el pasado';
    END IF;

    IF p_fecha_inicio < v_membresia.fecha_inicio
       OR p_fecha_inicio > v_membresia.fecha_fin THEN
        RAISE EXCEPTION 'La congelación debe comenzar dentro de la vigencia de la membresía';
    END IF;

    IF p_fecha_fin IS NOT NULL THEN
        IF p_fecha_fin < p_fecha_inicio
           OR p_fecha_fin > v_membresia.fecha_fin THEN
            RAISE EXCEPTION 'La fecha final de congelación no es válida';
        END IF;
    END IF;

    INSERT INTO congelacion_membresia (
        membresia_id, fecha_inicio, fecha_fin, motivo
    ) VALUES (
        p_membresia_id, p_fecha_inicio, p_fecha_fin, p_motivo
    )
    RETURNING congelacion_id INTO v_congelacion_id;

    PERFORM sincronizar_estados_membresia();
    RETURN v_congelacion_id;
END;
$$;

CREATE OR REPLACE FUNCTION cerrar_congelacion(
    p_congelacion_id BIGINT,
    p_fecha_fin DATE DEFAULT CURRENT_DATE
)
RETURNS VOID
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_membresia_id BIGINT;
    v_fecha_inicio DATE;
BEGIN
    SELECT membresia_id, fecha_inicio
      INTO v_membresia_id, v_fecha_inicio
      FROM congelacion_membresia
     WHERE congelacion_id = p_congelacion_id
       AND fecha_fin IS NULL
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No existe una congelación abierta con ID %', p_congelacion_id;
    END IF;

    IF p_fecha_fin IS NULL OR p_fecha_fin < v_fecha_inicio
       OR p_fecha_fin > CURRENT_DATE THEN
        RAISE EXCEPTION 'La fecha de término de congelación no es válida';
    END IF;

    UPDATE congelacion_membresia
       SET fecha_fin = p_fecha_fin
     WHERE congelacion_id = p_congelacion_id;

    PERFORM sincronizar_estados_membresia();
END;
$$;

-- ---------------------------------------------------------------------------
-- 7. VALIDACIÓN DE CAPACIDAD Y DISPONIBILIDAD DE SESIONES
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION validar_capacidad_sesion()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_capacidad_sala INTEGER;
    v_sala_activa BOOLEAN;
    v_instructor_activo BOOLEAN;
    v_cupos_ocupados INTEGER := 0;
BEGIN
    SELECT capacidad, activa
      INTO v_capacidad_sala, v_sala_activa
      FROM sala
     WHERE sala_id = NEW.sala_id;

    IF NOT FOUND OR NOT v_sala_activa THEN
        RAISE EXCEPTION 'La sala indicada no existe o está inactiva';
    END IF;

    IF NEW.cupos_totales > v_capacidad_sala THEN
        RAISE EXCEPTION 'Los cupos de la sesión (%) superan la capacidad de la sala (%)',
            NEW.cupos_totales, v_capacidad_sala;
    END IF;

    SELECT activo
      INTO v_instructor_activo
      FROM instructor
     WHERE instructor_id = NEW.instructor_id;

    IF NOT FOUND OR NOT v_instructor_activo THEN
        RAISE EXCEPTION 'El instructor indicado no existe o está inactivo';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        SELECT COUNT(*)::INTEGER
          INTO v_cupos_ocupados
          FROM reserva
         WHERE sesion_id = NEW.sesion_id
           AND estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE');

        IF NEW.cupos_totales < v_cupos_ocupados THEN
            RAISE EXCEPTION 'No se puede reducir la capacidad por debajo de las reservas confirmadas (%)',
                v_cupos_ocupados;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validar_capacidad_sesion
BEFORE INSERT OR UPDATE OF sala_id, instructor_id, cupos_totales
ON sesion_clase
FOR EACH ROW
EXECUTE FUNCTION validar_capacidad_sesion();

-- ---------------------------------------------------------------------------
-- 8. RESERVAS Y LISTA DE ESPERA (OPERACIONES TRANSACCIONALES)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION promover_lista_espera(p_sesion_id BIGINT)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_sesion sesion_clase%ROWTYPE;
    v_ocupados INTEGER;
    v_reserva_id BIGINT;
    v_promovidas INTEGER := 0;
BEGIN
    SELECT *
      INTO v_sesion
      FROM sesion_clase
     WHERE sesion_id = p_sesion_id
     FOR UPDATE;

    IF NOT FOUND OR v_sesion.estado <> 'PROGRAMADA'
       OR v_sesion.inicio <= CURRENT_TIMESTAMP THEN
        RETURN 0;
    END IF;

    LOOP
        SELECT COUNT(*)::INTEGER
          INTO v_ocupados
          FROM reserva
         WHERE sesion_id = p_sesion_id
           AND estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE');

        EXIT WHEN v_ocupados >= v_sesion.cupos_totales;

        -- Se promueve al primer socio de la cola que aún tenga membresía vigente.
        SELECT r.reserva_id
          INTO v_reserva_id
          FROM reserva r
         WHERE r.sesion_id = p_sesion_id
           AND r.estado = 'EN_ESPERA'
           AND socio_tiene_membresia_vigente(r.socio_id)
         ORDER BY r.creada_en, r.reserva_id
         LIMIT 1
         FOR UPDATE OF r;

        EXIT WHEN NOT FOUND;

        UPDATE reserva
           SET estado = 'RESERVADA'
         WHERE reserva_id = v_reserva_id;

        v_promovidas := v_promovidas + 1;
    END LOOP;

    RETURN v_promovidas;
END;
$$;

CREATE OR REPLACE FUNCTION reservar_clase(
    p_sesion_id BIGINT,
    p_socio_id BIGINT
)
RETURNS TABLE (
    reserva_id BIGINT,
    estado estado_reserva
)
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_sesion sesion_clase%ROWTYPE;
    v_ocupados INTEGER;
    v_estado estado_reserva;
    v_reserva_id BIGINT;
BEGIN
    -- El bloqueo serializa las reservas de una misma sesión y evita sobrecupos.
    SELECT *
      INTO v_sesion
      FROM sesion_clase
     WHERE sesion_id = p_sesion_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La sesión % no existe', p_sesion_id;
    END IF;

    IF v_sesion.estado <> 'PROGRAMADA' OR v_sesion.inicio <= CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'La sesión no admite nuevas reservas';
    END IF;

    PERFORM 1
      FROM socio
     WHERE socio_id = p_socio_id
       AND activo = TRUE
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El socio no existe o está inactivo';
    END IF;

    IF NOT socio_tiene_membresia_vigente(p_socio_id) THEN
        RAISE EXCEPTION 'El socio no tiene una membresía vigente';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM reserva
         WHERE sesion_id = p_sesion_id
           AND socio_id = p_socio_id
           AND estado <> 'CANCELADA'
    ) THEN
        RAISE EXCEPTION 'El socio ya tiene una reserva o está en lista de espera para esta sesión';
    END IF;

    SELECT COUNT(*)::INTEGER
      INTO v_ocupados
      FROM reserva
     WHERE sesion_id = p_sesion_id
       AND estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE');

    IF v_ocupados < v_sesion.cupos_totales THEN
        v_estado := 'RESERVADA';
    ELSE
        v_estado := 'EN_ESPERA';
    END IF;

    INSERT INTO reserva (sesion_id, socio_id, estado)
    VALUES (p_sesion_id, p_socio_id, v_estado)
    RETURNING reserva.reserva_id INTO v_reserva_id;

    RETURN QUERY SELECT v_reserva_id, v_estado;
END;
$$;

CREATE OR REPLACE FUNCTION cancelar_reserva(
    p_reserva_id BIGINT,
    p_socio_id BIGINT
)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_sesion_id BIGINT;
    v_sesion sesion_clase%ROWTYPE;
    v_reserva reserva%ROWTYPE;
    v_promovidas INTEGER := 0;
BEGIN
    SELECT sesion_id
      INTO v_sesion_id
      FROM reserva
     WHERE reserva_id = p_reserva_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La reserva % no existe', p_reserva_id;
    END IF;

    SELECT *
      INTO v_sesion
      FROM sesion_clase
     WHERE sesion_id = v_sesion_id
     FOR UPDATE;

    SELECT *
      INTO v_reserva
      FROM reserva
     WHERE reserva_id = p_reserva_id
     FOR UPDATE;

    IF v_reserva.socio_id <> p_socio_id THEN
        RAISE EXCEPTION 'El socio no puede cancelar una reserva que no le pertenece';
    END IF;

    IF v_reserva.estado NOT IN ('RESERVADA', 'EN_ESPERA') THEN
        RAISE EXCEPTION 'La reserva no se encuentra en un estado cancelable';
    END IF;

    IF v_sesion.estado <> 'PROGRAMADA'
       OR v_sesion.inicio <= CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'La reserva ya no se puede cancelar';
    END IF;

    UPDATE reserva
       SET estado = 'CANCELADA',
           cancelada_en = CURRENT_TIMESTAMP
     WHERE reserva_id = p_reserva_id;

    IF v_reserva.estado = 'RESERVADA' THEN
        v_promovidas := promover_lista_espera(v_sesion_id);
    END IF;

    RETURN v_promovidas;
END;
$$;

CREATE OR REPLACE FUNCTION cancelar_sesion_clase(p_sesion_id BIGINT)
RETURNS INTEGER
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_sesion sesion_clase%ROWTYPE;
    v_canceladas INTEGER;
BEGIN
    SELECT *
      INTO v_sesion
      FROM sesion_clase
     WHERE sesion_id = p_sesion_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La sesión % no existe', p_sesion_id;
    END IF;

    IF v_sesion.estado <> 'PROGRAMADA'
       OR v_sesion.inicio <= CURRENT_TIMESTAMP THEN
        RAISE EXCEPTION 'Solo se puede cancelar una sesión programada que aún no comienza';
    END IF;

    UPDATE sesion_clase
       SET estado = 'CANCELADA'
     WHERE sesion_id = p_sesion_id;

    UPDATE reserva
       SET estado = 'CANCELADA',
           cancelada_en = CURRENT_TIMESTAMP,
           asistio_en = NULL
     WHERE sesion_id = p_sesion_id
       AND estado IN ('RESERVADA', 'EN_ESPERA');

    GET DIAGNOSTICS v_canceladas = ROW_COUNT;
    RETURN v_canceladas;
END;
$$;

CREATE OR REPLACE FUNCTION registrar_asistencia_clase(
    p_reserva_id BIGINT,
    p_socio_id BIGINT,
    p_asistio BOOLEAN
)
RETURNS estado_reserva
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_sesion_id BIGINT;
    v_sesion sesion_clase%ROWTYPE;
    v_reserva reserva%ROWTYPE;
    v_nuevo_estado estado_reserva;
BEGIN
    SELECT sesion_id
      INTO v_sesion_id
      FROM reserva
     WHERE reserva_id = p_reserva_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'La reserva % no existe', p_reserva_id;
    END IF;

    SELECT *
      INTO v_sesion
      FROM sesion_clase
     WHERE sesion_id = v_sesion_id
     FOR UPDATE;

    SELECT *
      INTO v_reserva
      FROM reserva
     WHERE reserva_id = p_reserva_id
     FOR UPDATE;

    IF v_reserva.socio_id <> p_socio_id THEN
        RAISE EXCEPTION 'La reserva no pertenece al socio indicado';
    END IF;

    IF v_reserva.estado <> 'RESERVADA' THEN
        RAISE EXCEPTION 'Solo se puede registrar asistencia para una reserva confirmada';
    END IF;

    IF v_sesion.estado NOT IN ('EN_CURSO', 'FINALIZADA')
       OR CURRENT_TIMESTAMP < v_sesion.inicio THEN
        RAISE EXCEPTION 'La sesión aún no está habilitada para registrar asistencia';
    END IF;

    IF p_asistio THEN
        v_nuevo_estado := 'ASISTIO';
        UPDATE reserva
           SET estado = v_nuevo_estado,
               asistio_en = CURRENT_TIMESTAMP
         WHERE reserva_id = p_reserva_id;
    ELSE
        v_nuevo_estado := 'AUSENTE';
        UPDATE reserva
           SET estado = v_nuevo_estado
         WHERE reserva_id = p_reserva_id;
    END IF;

    RETURN v_nuevo_estado;
END;
$$;

-- ---------------------------------------------------------------------------
-- 9. REGISTRO TRANSACCIONAL DE ACCESOS QR Y CONTROL DE AFORO
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION registrar_acceso_qr(
    p_token TEXT,
    p_punto_acceso_id BIGINT,
    p_tipo tipo_evento_acceso
)
RETURNS TABLE (
    evento_id BIGINT,
    resultado resultado_acceso,
    motivo_rechazo VARCHAR
)
LANGUAGE plpgsql
SET search_path = fitlife, public
AS $$
DECLARE
    v_instalacion_id BIGINT;
    v_aforo_maximo INTEGER;
    v_tipo_punto tipo_punto_acceso;
    v_credencial credencial_qr%ROWTYPE;
    v_credencial_id BIGINT;
    v_socio_id BIGINT;
    v_socio_activo BOOLEAN;
    v_aforo_actual INTEGER;
    v_instalacion_presencia BIGINT;
    v_evento_id BIGINT;
    v_motivo VARCHAR(100);
BEGIN
    IF p_tipo IS NULL THEN
        RAISE EXCEPTION 'Debe indicar si el movimiento es ENTRADA o SALIDA';
    END IF;

    -- Bloquea la fila de instalación. Las entradas simultáneas se serializan
    -- para que no se supere el aforo máximo por una condición de carrera.
    SELECT pa.instalacion_id, pa.tipo, i.aforo_maximo
      INTO v_instalacion_id, v_tipo_punto, v_aforo_maximo
      FROM punto_acceso pa
      JOIN instalacion i ON i.instalacion_id = pa.instalacion_id
     WHERE pa.punto_acceso_id = p_punto_acceso_id
       AND pa.activo = TRUE
       AND i.activa = TRUE
     FOR UPDATE OF i;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'El punto de acceso no existe o está inactivo';
    END IF;

    IF v_tipo_punto = 'ENTRADA' AND p_tipo = 'SALIDA' THEN
        v_motivo := 'DIRECCION_NO_PERMITIDA';
    ELSIF v_tipo_punto = 'SALIDA' AND p_tipo = 'ENTRADA' THEN
        v_motivo := 'DIRECCION_NO_PERMITIDA';
    END IF;

    IF v_motivo IS NULL THEN
        IF p_token IS NULL OR BTRIM(p_token) = '' THEN
            v_motivo := 'TOKEN_VACIO';
        ELSE
            SELECT *
              INTO v_credencial
              FROM credencial_qr
             WHERE hash_token = public.digest(convert_to(p_token, 'UTF8'), 'sha256');

            IF NOT FOUND THEN
                v_motivo := 'CREDENCIAL_NO_RECONOCIDA';
            ELSE
                v_credencial_id := v_credencial.credencial_id;
                v_socio_id := v_credencial.socio_id;

                IF v_credencial.revocada_en IS NOT NULL THEN
                    v_motivo := 'CREDENCIAL_REVOCADA';
                ELSIF v_credencial.expira_en IS NOT NULL
                      AND v_credencial.expira_en <= CURRENT_TIMESTAMP THEN
                    v_motivo := 'CREDENCIAL_EXPIRADA';
                END IF;
            END IF;
        END IF;
    END IF;

    IF v_motivo IS NULL THEN
        SELECT activo
          INTO v_socio_activo
          FROM socio
         WHERE socio_id = v_socio_id
         FOR UPDATE;

        IF NOT FOUND OR NOT v_socio_activo THEN
            v_motivo := 'SOCIO_INACTIVO';
        ELSIF NOT socio_tiene_membresia_vigente(v_socio_id) THEN
            v_motivo := 'MEMBRESIA_NO_VIGENTE';
        END IF;
    END IF;

    IF v_motivo IS NULL AND p_tipo = 'ENTRADA' THEN
        IF EXISTS (
            SELECT 1 FROM presencia_actual WHERE socio_id = v_socio_id
        ) THEN
            v_motivo := 'SOCIO_YA_DENTRO';
        ELSE
            SELECT COUNT(*)::INTEGER
              INTO v_aforo_actual
              FROM presencia_actual pr
              JOIN evento_acceso ea
                ON ea.evento_id = pr.evento_entrada_id
              JOIN punto_acceso pa
                ON pa.punto_acceso_id = ea.punto_acceso_id
             WHERE pa.instalacion_id = v_instalacion_id;

            IF v_aforo_actual >= v_aforo_maximo THEN
                v_motivo := 'AFORO_COMPLETO';
            END IF;
        END IF;
    ELSIF v_motivo IS NULL AND p_tipo = 'SALIDA' THEN
        SELECT pa.instalacion_id
          INTO v_instalacion_presencia
          FROM presencia_actual pr
          JOIN evento_acceso ea
            ON ea.evento_id = pr.evento_entrada_id
          JOIN punto_acceso pa
            ON pa.punto_acceso_id = ea.punto_acceso_id
         WHERE pr.socio_id = v_socio_id
         FOR UPDATE OF pr;

        IF NOT FOUND THEN
            v_motivo := 'SOCIO_SIN_ENTRADA_REGISTRADA';
        ELSIF v_instalacion_presencia <> v_instalacion_id THEN
            v_motivo := 'SALIDA_EN_INSTALACION_DISTINTA';
        END IF;
    END IF;

    IF v_motivo IS NOT NULL THEN
        INSERT INTO evento_acceso (
            punto_acceso_id, credencial_id, tipo, resultado, motivo_rechazo
        ) VALUES (
            p_punto_acceso_id, v_credencial_id, p_tipo, 'RECHAZADO', v_motivo
        )
        RETURNING evento_acceso.evento_id INTO v_evento_id;

        RETURN QUERY
        SELECT v_evento_id, 'RECHAZADO'::resultado_acceso, v_motivo;
        RETURN;
    END IF;

    INSERT INTO evento_acceso (
        punto_acceso_id, credencial_id, tipo, resultado, motivo_rechazo
    ) VALUES (
        p_punto_acceso_id, v_credencial_id, p_tipo, 'AUTORIZADO', NULL
    )
    RETURNING evento_acceso.evento_id INTO v_evento_id;

    IF p_tipo = 'ENTRADA' THEN
        INSERT INTO presencia_actual (socio_id, evento_entrada_id)
        VALUES (v_socio_id, v_evento_id);
    ELSE
        DELETE FROM presencia_actual
         WHERE socio_id = v_socio_id;
    END IF;

    RETURN QUERY
    SELECT v_evento_id, 'AUTORIZADO'::resultado_acceso, NULL::VARCHAR;
END;
$$;

-- ---------------------------------------------------------------------------
-- 10. VISTAS PARA DASHBOARD Y CONSULTAS
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW vw_aforo_actual AS
SELECT
    i.instalacion_id,
    i.nombre AS instalacion,
    i.aforo_maximo,
    COUNT(p.socio_id)::INTEGER AS personas_presentes,
    GREATEST(
        i.aforo_maximo - COUNT(p.socio_id)::INTEGER,
        0
    ) AS cupos_disponibles,
    ROUND(
        (COUNT(p.socio_id)::NUMERIC / NULLIF(i.aforo_maximo, 0)) * 100,
        2
    ) AS porcentaje_ocupacion
FROM instalacion i
LEFT JOIN (
    SELECT
        pr.socio_id,
        pa.instalacion_id
    FROM presencia_actual pr
    JOIN evento_acceso ea
      ON ea.evento_id = pr.evento_entrada_id
    JOIN punto_acceso pa
      ON pa.punto_acceso_id = ea.punto_acceso_id
) p ON p.instalacion_id = i.instalacion_id
GROUP BY i.instalacion_id, i.nombre, i.aforo_maximo;

CREATE OR REPLACE VIEW vw_disponibilidad_clases AS
SELECT
    sc.sesion_id,
    a.nombre AS actividad,
    pe.nombres || ' ' || pe."apellidoPaterno" || ' ' || pe."apellidoMaterno" AS instructor,
    sa.nombre AS sala,
    sc.inicio,
    sc.fin,
    sc.estado,
    sc.cupos_totales,
    COUNT(r.reserva_id) FILTER (
        WHERE r.estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE')
    )::INTEGER AS cupos_ocupados,
    GREATEST(
        sc.cupos_totales - COUNT(r.reserva_id) FILTER (
            WHERE r.estado IN ('RESERVADA', 'ASISTIO', 'AUSENTE')
        )::INTEGER,
        0
    ) AS cupos_disponibles,
    COUNT(r.reserva_id) FILTER (
        WHERE r.estado = 'EN_ESPERA'
    )::INTEGER AS personas_en_espera
FROM sesion_clase sc
JOIN actividad a ON a.actividad_id = sc.actividad_id
JOIN instructor ins ON ins.instructor_id = sc.instructor_id
JOIN persona pe ON pe.rut = ins.persona_id
JOIN sala sa ON sa.sala_id = sc.sala_id
LEFT JOIN reserva r ON r.sesion_id = sc.sesion_id
GROUP BY
    sc.sesion_id, a.nombre, pe.nombres, pe."apellidoPaterno", pe."apellidoMaterno",
    sa.nombre, sc.inicio, sc.fin, sc.estado, sc.cupos_totales;

CREATE OR REPLACE VIEW vw_lista_espera AS
SELECT
    r.reserva_id,
    r.sesion_id,
    r.socio_id,
    pe.nombres || ' ' || pe."apellidoPaterno" || ' ' || pe."apellidoMaterno" AS socio,
    ROW_NUMBER() OVER (
        PARTITION BY r.sesion_id
        ORDER BY r.creada_en, r.reserva_id
    ) AS posicion_espera,
    r.creada_en
FROM reserva r
JOIN socio s ON s.socio_id = r.socio_id
JOIN persona pe ON pe.rut = s.persona_id
WHERE r.estado = 'EN_ESPERA';

CREATE OR REPLACE VIEW vw_membresias AS
SELECT
    m.membresia_id,
    m.socio_id,
    pe.nombres || ' ' || pe."apellidoPaterno" || ' ' || pe."apellidoMaterno" AS socio,
    pm.nombre AS plan,
    m.estado,
    m.fecha_inicio,
    m.fecha_fin,
    m.precio_acordado,
    CASE
        WHEN m.estado = 'CANCELADA' THEN 'CANCELADA'
        WHEN m.fecha_fin < CURRENT_DATE THEN 'VENCIDA'
        WHEN EXISTS (
            SELECT 1
            FROM congelacion_membresia c
            WHERE c.membresia_id = m.membresia_id
              AND CURRENT_DATE >= c.fecha_inicio
              AND (c.fecha_fin IS NULL OR CURRENT_DATE <= c.fecha_fin)
        ) THEN 'CONGELADA'
        ELSE 'ACTIVA'
    END AS estado_calculado
FROM membresia m
JOIN socio s ON s.socio_id = m.socio_id
JOIN persona pe ON pe.rut = s.persona_id
JOIN plan_membresia pm ON pm.plan_id = m.plan_id;

CREATE OR REPLACE VIEW vw_accesos_recientes AS
SELECT
    ea.evento_id,
    ea.registrado_en,
    ea.tipo,
    ea.resultado,
    ea.motivo_rechazo,
    pa.nombre AS punto_acceso,
    i.nombre AS instalacion,
    pe.nombres || ' ' || pe."apellidoPaterno" || ' ' || pe."apellidoMaterno" AS socio
FROM evento_acceso ea
JOIN punto_acceso pa ON pa.punto_acceso_id = ea.punto_acceso_id
JOIN instalacion i ON i.instalacion_id = pa.instalacion_id
LEFT JOIN credencial_qr cq ON cq.credencial_id = ea.credencial_id
LEFT JOIN socio s ON s.socio_id = cq.socio_id
LEFT JOIN persona pe ON pe.rut = s.persona_id;

-- ---------------------------------------------------------------------------
-- 11. DATOS INICIALES DE CATÁLOGO
-- ---------------------------------------------------------------------------

INSERT INTO rol (codigo, descripcion) VALUES
    ('ADMINISTRADOR', 'Administración general de la plataforma'),
    ('RECEPCIONISTA', 'Control de acceso y atención de socios'),
    ('INSTRUCTOR', 'Gestión de sesiones y asistencia de clases'),
    ('SOCIO', 'Acceso a membresías y reservas de clases')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO actividad (nombre, descripcion) VALUES
    ('Spinning', 'Actividad grupal de ciclismo indoor'),
    ('Yoga', 'Actividad grupal de movilidad, respiración y equilibrio')
ON CONFLICT (nombre) DO NOTHING;

COMMIT;

-- ============================================================================
-- 12. EJEMPLOS DE USO (DESCOMENTAR Y ADAPTAR)
-- ============================================================================
--
-- 12.1. Sincronizar estados de membresías (ejecutar periódicamente desde el backend):
-- SELECT fitlife.sincronizar_estados_membresia();
--
-- 12.2. Reservar una clase:
-- SELECT * FROM fitlife.reservar_clase(1, 1);
--
-- 12.3. Cancelar una reserva (devuelve cuántas personas fueron promovidas):
-- SELECT fitlife.cancelar_reserva(1, 1);
--
-- 12.4. Validar un QR (el token en texto plano se genera en el backend; nunca se guarda):
-- SELECT * FROM fitlife.registrar_acceso_qr(
--     'TOKEN_ALEATORIO_GENERADO_POR_EL_BACKEND',
--     1,
--     'ENTRADA'
-- );
--
-- 12.5. Consultar aforo:
-- SELECT * FROM fitlife.vw_aforo_actual;
--
-- 12.6. Consultar disponibilidad de clases:
-- SELECT * FROM fitlife.vw_disponibilidad_clases;
--
-- 12.7. Consultar lista de espera:
-- SELECT * FROM fitlife.vw_lista_espera WHERE sesion_id = 1;
-- ============================================================================
