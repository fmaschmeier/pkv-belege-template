-- =====================================================
-- Storage Policies Cleanup Script
-- Führe dieses Script im Supabase SQL Editor aus
-- =====================================================

-- 1. Zeige alle aktuellen Storage Policies
SELECT policyname, cmd,
       CASE
         WHEN qual LIKE '%settlements%' THEN 'settlements'
         WHEN qual LIKE '%receipts%' THEN 'receipts'
         ELSE 'other'
       END as bucket
FROM pg_policies
WHERE schemaname = 'storage' AND tablename = 'objects'
ORDER BY bucket, cmd, policyname;

-- =====================================================
-- 2. Lösche die doppelten/alten Policies für settlements
-- WICHTIG: Passe die Policy-Namen an basierend auf dem
-- Ergebnis von Query 1!
-- =====================================================

-- Beispiel: Wenn du Policies mit ähnlichen Namen hast wie:
-- "Allow authenticated uploads to settlements" (neu)
-- "Allow authenticated uploads to settlements 1" (alt/duplikat)
--
-- Dann lösche die alten so:

-- DROP POLICY IF EXISTS "settlements_select_policy" ON storage.objects;
-- DROP POLICY IF EXISTS "settlements_insert_policy" ON storage.objects;
-- DROP POLICY IF EXISTS "settlements_update_policy" ON storage.objects;
-- DROP POLICY IF EXISTS "settlements_delete_policy" ON storage.objects;

-- =====================================================
-- 3. Falls du komplett neu aufsetzen willst:
-- Lösche ALLE settlements Policies und erstelle 4 neue
-- =====================================================

-- Schritt A: Alle settlements Policies löschen (auskommentiert zur Sicherheit)
/*
DO $$
DECLARE
    pol RECORD;
BEGIN
    FOR pol IN
        SELECT policyname
        FROM pg_policies
        WHERE schemaname = 'storage'
          AND tablename = 'objects'
          AND qual LIKE '%settlements%'
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS %I ON storage.objects', pol.policyname);
        RAISE NOTICE 'Dropped policy: %', pol.policyname;
    END LOOP;
END $$;
*/

-- Schritt B: 4 neue Standard-Policies erstellen
/*
-- SELECT Policy
CREATE POLICY "settlements_authenticated_select" ON storage.objects
FOR SELECT TO authenticated
USING (bucket_id = 'settlements');

-- INSERT Policy
CREATE POLICY "settlements_authenticated_insert" ON storage.objects
FOR INSERT TO authenticated
WITH CHECK (bucket_id = 'settlements');

-- UPDATE Policy
CREATE POLICY "settlements_authenticated_update" ON storage.objects
FOR UPDATE TO authenticated
USING (bucket_id = 'settlements')
WITH CHECK (bucket_id = 'settlements');

-- DELETE Policy
CREATE POLICY "settlements_authenticated_delete" ON storage.objects
FOR DELETE TO authenticated
USING (bucket_id = 'settlements');
*/

-- =====================================================
-- 4. Verifiziere das Ergebnis
-- =====================================================
-- SELECT policyname, cmd FROM pg_policies
-- WHERE schemaname = 'storage' AND tablename = 'objects'
-- ORDER BY policyname;
