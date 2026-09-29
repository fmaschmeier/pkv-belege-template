-- Rohwerte der Beleg-Extraktion (Claude oder Regex-Parser), damit Korrekturen nachvollziehbar bleiben
ALTER TABLE submitted_receipts
    ADD COLUMN IF NOT EXISTS parsed_params JSONB;

COMMENT ON COLUMN submitted_receipts.parsed_params IS 'Ausgelesene Rohwerte des Belegs (JSON), von der API beim Import und beim Neu-Auslesen geschrieben';
