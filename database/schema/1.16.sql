-- FitLife 1.16: cada teléfono solo puede pertenecer a una persona.
BEGIN;
SET LOCAL search_path TO fitlife, public;

CREATE UNIQUE INDEX uq_persona_telefono
    ON persona ((
        CASE
            WHEN length(regexp_replace(telefono, '[^0-9]', '', 'g')) = 11
                 AND left(regexp_replace(telefono, '[^0-9]', '', 'g'), 2) = '56'
            THEN substring(regexp_replace(telefono, '[^0-9]', '', 'g') FROM 3)
            ELSE regexp_replace(telefono, '[^0-9]', '', 'g')
        END
    ))
    WHERE telefono IS NOT NULL AND BTRIM(telefono) <> '';

COMMIT;
