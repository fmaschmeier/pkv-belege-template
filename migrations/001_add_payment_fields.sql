-- Migration: Add payment fields to submitted_receipts
-- Diese Felder ermöglichen die QR-Code Generierung für SEPA-Überweisungen

ALTER TABLE submitted_receipts
ADD COLUMN IF NOT EXISTS payment_recipient VARCHAR(70),  -- Empfängername (max 70 Zeichen laut SEPA)
ADD COLUMN IF NOT EXISTS payment_iban VARCHAR(34),       -- IBAN (max 34 Zeichen)
ADD COLUMN IF NOT EXISTS payment_reference VARCHAR(140); -- Verwendungszweck (max 140 Zeichen laut SEPA)

-- Kommentare für Dokumentation
COMMENT ON COLUMN submitted_receipts.payment_recipient IS 'Überweisungsempfänger für SEPA-Zahlung';
COMMENT ON COLUMN submitted_receipts.payment_iban IS 'IBAN des Zahlungsempfängers';
COMMENT ON COLUMN submitted_receipts.payment_reference IS 'Verwendungszweck für SEPA-Zahlung';
