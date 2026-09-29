-- pkv-belege-template – Datenbankschema (Supabase/PostgreSQL)
-- Einrichtung: erst diese Datei, dann migrations/ in Nummernfolge (001, 002, …).
-- Zusammen ergeben sie denselben Stand wie die laufende Instanz (geprüft 2026-10-04).
--
-- Dieses Schema enthält alle Tabellen für die Verwaltung von:
-- - Leistungsabrechnungen (settlements)
-- - Einzelpositionen (settlement_items)
-- - Banktransaktionen (bank_transactions)
-- - Eingereichte Belege (submitted_receipts)
-- - Matching-Regeln (matching_rules)
-- - Korrektur-Regeln (correction_rules)
--
-- Inklusive Row Level Security (RLS) Policies

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Trigger für updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- Tabelle: settlements (Leistungsabrechnungen)
-- ============================================
CREATE TABLE IF NOT EXISTS settlements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    settlement_number VARCHAR(20) NOT NULL UNIQUE,  -- z.B. R/26/117
    settlement_date DATE NOT NULL,                   -- Erstattungsdatum
    insurance_number VARCHAR(20) NOT NULL,           -- z.B. 12345678
    total_invoiced DECIMAL(10,2),                    -- Summe Rechnungsbeträge
    total_reimbursed DECIMAL(10,2),                  -- Auszahlungsbetrag
    pdf_filename VARCHAR(255) NOT NULL,              -- Original-PDF Name
    pdf_url TEXT,                                    -- Storage-Pfad (z.B. {uuid}/datei.pdf)
    raw_text TEXT,                                   -- Geparster Text aus PDF
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_settlements_date ON settlements(settlement_date);
CREATE INDEX IF NOT EXISTS idx_settlements_number ON settlements(settlement_number);

-- Trigger
DROP TRIGGER IF EXISTS settlements_updated_at ON settlements;
CREATE TRIGGER settlements_updated_at
    BEFORE UPDATE ON settlements
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================
-- Tabelle: settlement_items (Einzelpositionen)
-- ============================================
CREATE TABLE IF NOT EXISTS settlement_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    settlement_id UUID NOT NULL REFERENCES settlements(id) ON DELETE CASCADE,
    receipt_number VARCHAR(20) NOT NULL,             -- z.B. B/26/1201
    insured_person VARCHAR(100) NOT NULL,            -- Max Mustermann
    insured_birthdate DATE,                          -- YYYY-MM-DD
    description VARCHAR(255),                        -- Linden-Apotheke, Rezept/Quittung
    treatment_period VARCHAR(50),                    -- 30.10.-04.11.2025
    invoice_amount DECIMAL(10,2),                    -- Rechnungsbetrag
    tariff VARCHAR(20),                              -- A100, uA155, PVN
    receipt_portion DECIMAL(10,2),                   -- Rechnungsanteil
    corrected_amount DECIMAL(10,2),                  -- korrigiert
    deferred_amount DECIMAL(10,2),                   -- zurückgestellt
    reimbursable_amount DECIMAL(10,2),               -- erstattungsfähig
    own_contribution DECIMAL(10,2),                  -- tariflicher Eigenanteil
    deductible DECIMAL(10,2),                        -- Selbstbeteiligung
    reimbursed_amount DECIMAL(10,2),                 -- Erstattungsbetrag
    notes TEXT[],                                    -- Anmerkungen der PKV (je Hinweis ein Eintrag)
    payment_status VARCHAR(20) DEFAULT 'pending',    -- pending/paid_by_bank/paid_cash/not_applicable
    payment_note TEXT,                               -- z.B. "Rezept bar bezahlt"
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_items_settlement ON settlement_items(settlement_id);
CREATE INDEX IF NOT EXISTS idx_items_receipt ON settlement_items(receipt_number);
CREATE INDEX IF NOT EXISTS idx_items_person ON settlement_items(insured_person);
CREATE INDEX IF NOT EXISTS idx_items_treatment ON settlement_items(treatment_period);

-- ============================================
-- Tabelle: bank_transactions (Banktransaktionen)
-- ============================================
CREATE TABLE IF NOT EXISTS bank_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_date DATE NOT NULL,                      -- Buchungstag
    value_date DATE NOT NULL,                        -- Wertstellung
    transaction_type VARCHAR(50),                    -- Umsatzart
    description TEXT NOT NULL,                       -- Buchungstext
    amount DECIMAL(10,2) NOT NULL,                   -- Betrag (positiv = Einnahme)
    currency VARCHAR(3) DEFAULT 'EUR',               -- Währung
    iban VARCHAR(34),                                -- IBAN Kontoinhaber
    category VARCHAR(100),                           -- Bank-Kategorie
    settlement_id UUID REFERENCES settlements(id),   -- Zugeordnete Abrechnung
    is_universa_payment BOOLEAN DEFAULT FALSE,       -- Ist Universa-Erstattung?
    import_hash VARCHAR(64) UNIQUE,                  -- Hash für Duplikat-Erkennung
    imported_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_bank_booking_date ON bank_transactions(booking_date);
CREATE INDEX IF NOT EXISTS idx_bank_settlement ON bank_transactions(settlement_id);
CREATE INDEX IF NOT EXISTS idx_bank_universa ON bank_transactions(is_universa_payment);

-- ============================================
-- Tabelle: submitted_receipts (Eingereichte Belege)
-- ============================================
CREATE TABLE IF NOT EXISTS submitted_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Metadaten
    submission_date DATE NOT NULL,                   -- PDF Erstellungsdatum
    pdf_filename VARCHAR(255) NOT NULL,
    pdf_hash VARCHAR(64) UNIQUE,                     -- SHA256 für Duplikaterkennung
    pdf_url VARCHAR,                                 -- Storage-Pfad (z.B. {uuid}/datei.pdf)
    raw_text TEXT,                                   -- Geparster Text aus PDF

    -- Aus Dateiname geparst
    filename_person VARCHAR(100),                    -- Mila, Ben, Helga
    filename_provider VARCHAR(100),                  -- Entlastung, Apotheke

    -- Aus PDF extrahiert
    receipt_type VARCHAR(20),                        -- rezept/arzt/hilfsmittel/pflege/sonstige
    provider_name VARCHAR(200),                      -- Familienentlastender Dienst Musterstadt e.V.
    provider_address TEXT,
    invoice_number VARCHAR(50),
    invoice_date DATE,
    invoice_amount DECIMAL(10,2),

    -- Versicherte Person
    insured_person VARCHAR(100),
    insured_birthdate DATE,

    -- Leistungsdetails
    description TEXT,
    treatment_period VARCHAR(50),                    -- z.B. "03.12.-18.12.2025"

    -- Fälligkeit
    due_date DATE,
    due_date_source VARCHAR(20),                     -- explicit/calculated

    -- Status-Tracking Erstattung (durch PKV)
    status VARCHAR(20) DEFAULT 'submitted',          -- submitted/reimbursed/partial/rejected/pending
    settlement_item_id UUID,                         -- FK wenn erstattet (keine harte Referenz)
    reimbursed_amount DECIMAL(10,2),
    reimbursed_date DATE,
    rejection_reason TEXT,

    -- Status-Tracking Zahlung (durch User an Anbieter)
    payment_transaction_id UUID,                     -- FK zu bank_transactions
    paid_date DATE,
    paid_amount DECIMAL(10,2),                       -- Bezahlter Betrag (für Teilzahlungen)

    -- Zahlungsdaten für QR-Code
    payment_recipient VARCHAR(70),                   -- Überweisungsempfänger
    payment_iban VARCHAR(34),                        -- IBAN
    payment_reference VARCHAR(140),                  -- Verwendungszweck

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_receipts_submission_date ON submitted_receipts(submission_date);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON submitted_receipts(status);
CREATE INDEX IF NOT EXISTS idx_receipts_person ON submitted_receipts(insured_person);
CREATE INDEX IF NOT EXISTS idx_receipts_due_date ON submitted_receipts(due_date);

-- Trigger
DROP TRIGGER IF EXISTS receipts_updated_at ON submitted_receipts;
CREATE TRIGGER receipts_updated_at
    BEFORE UPDATE ON submitted_receipts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================
-- Tabelle: matching_rules (Beleg-zu-Zahlung Matching)
-- ============================================
CREATE TABLE IF NOT EXISTS matching_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_pattern VARCHAR NOT NULL,               -- Pattern im Provider-Namen (case-insensitive)
    bank_patterns TEXT[] NOT NULL,                   -- Patterns im Banktext (case-insensitive)
    match_type VARCHAR DEFAULT 'provider',           -- provider/verhinderungspflege
    priority INT DEFAULT 0,                          -- Höhere Priorität wird zuerst geprüft
    active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_matching_rules_active ON matching_rules(active, priority DESC);

-- Trigger
CREATE OR REPLACE FUNCTION update_matching_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_matching_rules_updated_at ON matching_rules;
CREATE TRIGGER trigger_matching_rules_updated_at
    BEFORE UPDATE ON matching_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_matching_rules_updated_at();

-- ============================================
-- Tabelle: correction_rules (Parser-Korrekturen)
-- ============================================
CREATE TABLE IF NOT EXISTS correction_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    field_name VARCHAR NOT NULL,                     -- z.B. 'provider_name', 'insured_person'
    raw_value VARCHAR NOT NULL,                      -- Original-Wert aus Parser
    corrected_value VARCHAR NOT NULL,                -- Korrigierter Wert
    active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_correction_rules_lookup
    ON correction_rules(field_name, raw_value)
    WHERE active = true;

CREATE UNIQUE INDEX IF NOT EXISTS idx_correction_rules_unique
    ON correction_rules(field_name, raw_value)
    WHERE active = true;

-- Trigger
CREATE OR REPLACE FUNCTION update_correction_rules_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_correction_rules_updated_at ON correction_rules;
CREATE TRIGGER trigger_correction_rules_updated_at
    BEFORE UPDATE ON correction_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_correction_rules_updated_at();

-- ============================================
-- Tabelle: provider_payment_info (Gespeicherte Zahlungsdaten)
-- ============================================
CREATE TABLE IF NOT EXISTS provider_payment_info (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_pattern VARCHAR NOT NULL UNIQUE,        -- Anbieter-Name (normalisiert)
    payment_recipient VARCHAR(70),                   -- Überweisungsempfänger
    payment_iban VARCHAR(34),                        -- IBAN
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_provider_payment_active
    ON provider_payment_info(provider_pattern)
    WHERE active = true;

-- Trigger
CREATE OR REPLACE FUNCTION update_provider_payment_info_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_provider_payment_info_updated_at ON provider_payment_info;
CREATE TRIGGER trigger_provider_payment_info_updated_at
    BEFORE UPDATE ON provider_payment_info
    FOR EACH ROW
    EXECUTE FUNCTION update_provider_payment_info_updated_at();

-- ============================================
-- VIEWS
-- ============================================

-- Übersicht aller Positionen mit Settlement-Info
CREATE OR REPLACE VIEW v_settlement_items AS
SELECT
    si.*,
    s.settlement_number,
    s.settlement_date,
    s.pdf_filename
FROM settlement_items si
JOIN settlements s ON si.settlement_id = s.id
ORDER BY s.settlement_date DESC, si.receipt_number;

-- Zusammenfassung pro Person
CREATE OR REPLACE VIEW v_person_summary AS
SELECT
    insured_person,
    insured_birthdate,
    COUNT(*) as total_items,
    SUM(invoice_amount) as total_invoiced,
    SUM(reimbursed_amount) as total_reimbursed,
    MIN(s.settlement_date) as first_settlement,
    MAX(s.settlement_date) as last_settlement
FROM settlement_items si
JOIN settlements s ON si.settlement_id = s.id
GROUP BY insured_person, insured_birthdate
ORDER BY insured_person;

-- Offene Erstattungen
CREATE OR REPLACE VIEW v_pending_payments AS
SELECT
    s.settlement_number,
    s.settlement_date,
    s.total_reimbursed,
    s.pdf_filename,
    CASE
        WHEN bt.id IS NOT NULL THEN 'matched'
        ELSE 'pending'
    END as bank_status
FROM settlements s
LEFT JOIN bank_transactions bt ON bt.settlement_id = s.id
ORDER BY s.settlement_date DESC;

-- Item-Status Übersicht
CREATE OR REPLACE VIEW v_item_payment_status AS
SELECT
    si.receipt_number,
    si.insured_person,
    si.description,
    si.treatment_period,
    si.invoice_amount,
    si.reimbursed_amount,
    si.payment_status,
    si.payment_note,
    s.settlement_number,
    s.settlement_date
FROM settlement_items si
JOIN settlements s ON si.settlement_id = s.id
ORDER BY s.settlement_date DESC, si.receipt_number;

-- Offene Belege
CREATE OR REPLACE VIEW v_pending_receipts AS
SELECT
    id,
    submission_date,
    insured_person,
    provider_name,
    invoice_number,
    invoice_amount,
    due_date,
    CURRENT_DATE - submission_date AS days_pending,
    CASE
        WHEN due_date < CURRENT_DATE THEN 'overdue'
        WHEN due_date < CURRENT_DATE + INTERVAL '7 days' THEN 'due_soon'
        ELSE 'ok'
    END AS urgency
FROM submitted_receipts
WHERE status = 'submitted'
ORDER BY due_date ASC;

-- ============================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================
-- Nur authentifizierte Benutzer haben Zugriff

-- RLS aktivieren
ALTER TABLE settlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE settlement_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE bank_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE submitted_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE matching_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE correction_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE provider_payment_info ENABLE ROW LEVEL SECURITY;

-- Alte Policies löschen (falls vorhanden)
DROP POLICY IF EXISTS "Authenticated users full access" ON settlements;
DROP POLICY IF EXISTS "Authenticated users full access" ON settlement_items;
DROP POLICY IF EXISTS "Authenticated users full access" ON bank_transactions;
DROP POLICY IF EXISTS "Authenticated users full access" ON submitted_receipts;
DROP POLICY IF EXISTS "Authenticated users full access" ON matching_rules;
DROP POLICY IF EXISTS "Authenticated users full access" ON correction_rules;
DROP POLICY IF EXISTS "Authenticated users full access" ON provider_payment_info;

-- Policies: Nur authentifizierte User haben Zugriff
CREATE POLICY "Authenticated users full access" ON settlements
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Authenticated users full access" ON settlement_items
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Authenticated users full access" ON bank_transactions
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Authenticated users full access" ON submitted_receipts
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Authenticated users full access" ON matching_rules
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Authenticated users full access" ON correction_rules
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Authenticated users full access" ON provider_payment_info
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- ============================================
-- STORAGE POLICIES (für Supabase Storage)
-- ============================================
-- Nur authentifizierte Benutzer haben Zugriff auf Buckets

-- Alte Storage Policies löschen
DROP POLICY IF EXISTS "Allow all read settlements" ON storage.objects;
DROP POLICY IF EXISTS "Allow all upload settlements" ON storage.objects;
DROP POLICY IF EXISTS "Allow all update settlements" ON storage.objects;
DROP POLICY IF EXISTS "Allow all delete settlements" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated read settlements storage" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated upload settlements storage" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated update settlements storage" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated delete settlements storage" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated read receipts storage" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated upload receipts storage" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated update receipts storage" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated delete receipts storage" ON storage.objects;

-- Settlements Bucket
CREATE POLICY "Authenticated read settlements storage"
ON storage.objects FOR SELECT
TO authenticated
USING (bucket_id = 'settlements');

CREATE POLICY "Authenticated upload settlements storage"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'settlements');

CREATE POLICY "Authenticated update settlements storage"
ON storage.objects FOR UPDATE
TO authenticated
USING (bucket_id = 'settlements');

CREATE POLICY "Authenticated delete settlements storage"
ON storage.objects FOR DELETE
TO authenticated
USING (bucket_id = 'settlements');

-- Receipts Bucket
CREATE POLICY "Authenticated read receipts storage"
ON storage.objects FOR SELECT
TO authenticated
USING (bucket_id = 'receipts');

CREATE POLICY "Authenticated upload receipts storage"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'receipts');

CREATE POLICY "Authenticated update receipts storage"
ON storage.objects FOR UPDATE
TO authenticated
USING (bucket_id = 'receipts');

CREATE POLICY "Authenticated delete receipts storage"
ON storage.objects FOR DELETE
TO authenticated
USING (bucket_id = 'receipts');
