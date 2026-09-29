-- Migration: Add updated_at trigger for all tables with updated_at column
-- Run this in Supabase SQL Editor

-- Create the trigger function (if not exists)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add triggers to all tables with updated_at column

-- settlements
DROP TRIGGER IF EXISTS update_settlements_updated_at ON settlements;
CREATE TRIGGER update_settlements_updated_at
    BEFORE UPDATE ON settlements
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- settlement_items
DROP TRIGGER IF EXISTS update_settlement_items_updated_at ON settlement_items;
CREATE TRIGGER update_settlement_items_updated_at
    BEFORE UPDATE ON settlement_items
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- submitted_receipts
DROP TRIGGER IF EXISTS update_submitted_receipts_updated_at ON submitted_receipts;
CREATE TRIGGER update_submitted_receipts_updated_at
    BEFORE UPDATE ON submitted_receipts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- matching_rules
DROP TRIGGER IF EXISTS update_matching_rules_updated_at ON matching_rules;
CREATE TRIGGER update_matching_rules_updated_at
    BEFORE UPDATE ON matching_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- correction_rules
DROP TRIGGER IF EXISTS update_correction_rules_updated_at ON correction_rules;
CREATE TRIGGER update_correction_rules_updated_at
    BEFORE UPDATE ON correction_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- provider_payment_info
DROP TRIGGER IF EXISTS update_provider_payment_info_updated_at ON provider_payment_info;
CREATE TRIGGER update_provider_payment_info_updated_at
    BEFORE UPDATE ON provider_payment_info
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
