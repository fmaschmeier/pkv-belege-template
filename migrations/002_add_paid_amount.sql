-- Migration: Add paid_amount to submitted_receipts
-- Speichert den tatsächlich bezahlten Betrag für Teilzahlungen
-- Erstellt: 2026-01-17

ALTER TABLE submitted_receipts
ADD COLUMN IF NOT EXISTS paid_amount DECIMAL(10,2);  -- Bezahlter Betrag (kann < invoice_amount sein)

-- Kommentar für Dokumentation
COMMENT ON COLUMN submitted_receipts.paid_amount IS 'Bezahlter Betrag aus verknüpfter Transaktion. Bei Teilzahlungen < invoice_amount.';
