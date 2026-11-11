-- FitLife 1.9: registra Webpay como medio de pago de membresías.
-- Ejecutar después de 1.8.sql sobre una base FitLife existente.

ALTER TYPE fitlife.metodo_pago ADD VALUE IF NOT EXISTS 'WEBPAY';
