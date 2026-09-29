# Synthetische Beispielbelege

Frei erfundene Belege und Leistungsabrechnungen, mit denen sich der ganze Ablauf
ausprobieren lässt: Beleg einlesen, Abrechnung einlesen, beides abgleichen. Es sind keine
echten Personen, Praxen, Beträge oder Bankverbindungen enthalten. Jede Seite trägt ein
„MUSTER"-Wasserzeichen und einen Hinweis in der Fußzeile.

| Ordner / Datei | Inhalt |
|---|---|
| `belege/` | 21 Belege mit Textebene, Dateinamen im Schema `NNN_Anbieter_Betrag_Person_PKVB.pdf` |
| `scans/` | dieselben 21 Belege als reine Bild-PDFs, wie ein Handy-Scan (Eingabe für den Claude-Vision-Weg) |
| `abrechnungen/` | 3 Leistungsabrechnungen, die genau diese Belege erstatten, und 1 Versichererbrief; dazu pdf.co-Fixtures (`*.pdfco-header.txt`, `*.pdfco.csv`) |
| `manifest.json` | Soll-Werte je Dokument: Belegart, Anbieter, Zahlungsempfänger, IBAN, Rechnungsnummer, Datum, Betrag, Person, Zuordnung zur Abrechnung |
| `generate_samples.py` | erzeugt alles neu, bei jedem Lauf byte-identisch |
| `verify_samples.py` | lässt die Parser dieses Repos offline gegen die Beispiele laufen |

## Der erfundene Haushalt

| Person | geboren | Vertrag | Belege |
|---|---|---|---|
| Jonas Beispiel | 14.03.1980 | 40012345, 150 € Selbstbeteiligung | Hausarzt, Labor, Augenarzt, Apotheke |
| Miriam Beispiel | 22.09.1983 | 40012345, 150 € Selbstbeteiligung | Zahnarzt (GOZ), Psychotherapie |
| Mila Beispiel | 05.06.2013 | 40012345 | Kinderarzt über Verrechnungsstelle, Apotheke, Optiker |
| Ben Beispiel | 17.11.2016 | 40012345 | HNO über Verrechnungsstelle, Ergotherapie, Klinik, Kinderarzt, Apotheke, Impfstoff |
| Helga Beispiel | 02.02.1942 | 40067890, Pflegegrad 3 | 2 × Verhinderungspflege (Formular), 2 × Entlastungsbetrag, Beratungseinsatz, Rollator |

Alle wohnen im Musterweg 7, 12345 Musterstadt. Alle Praxen sitzen in Musterstadt, alle
E-Mail-Adressen enden auf `.example` (reservierte Domain).

Für den Dateinamen-Abgleich: `INSURED_PERSONS=Jonas,Miriam,Mila,Ben,Helga`.

## Was die Beispiele abdecken

- **Belegarten** wie in echten Einreichungen: Arzt direkt und über Verrechnungsstelle,
  Zahnarzt über Abrechnungsgesellschaft, Labor, Psychotherapie, Klinikambulanz, Heilmittel,
  Apotheken-Kassenbon, Optiker, Sanitätshaus, Pflegedienst, Entlastungsdienst, das
  Verhinderungspflege-Formular des Versicherers.
- **Nachgerechnete Beträge**: GOÄ-Punktwert 5,82873 Cent, GOZ-Punktwert 5,62421 Cent,
  Einzelbetrag = Punkte × Punktwert × Faktor. Eine Position liegt über dem Schwellenwert
  (Faktor 3,5 mit Begründung).
- **Erstattungslogik** in den Abrechnungen: jährliche Selbstbeteiligung, tariflicher
  Eigenanteil (80 %), Höchstbeträge (Sehhilfe, Heilmittel), Kürzung auf den 2,3-fachen Satz,
  zurückgestellter Betrag (Entlastungsbetrag über 131 € im Monat), ein Beleg auf zwei Tarife
  verteilt.
- **Zahlungsempfänger** je Beleg mit eigener IBAN. Die IBANs sind prüfsummengültig, tragen
  aber die nicht vergebene Bankleitzahl 000 000 00, eine Überweisung erreicht also kein Konto.

Die Beispiele sind Testdaten, keine Abrechnungsberatung. Gebührenziffern, Punktzahlen und
Tarifregeln sind plausibel gewählt, nicht amtlich geprüft.

## Neu erzeugen und prüfen

```bash
pip install -r samples/requirements.txt
python samples/generate_samples.py          # --no-scans überspringt die Bild-PDFs
python samples/verify_samples.py            # --strict: Exit 1 auch bei Beleg-Abweichungen
```

`verify_samples.py` braucht weder pdf.co noch Supabase. Beide Parser lesen pdf.co-Ergebnisse
aus ihrem Cache; das Skript legt die Fixtures in einem temporären Cache ab.

- **Belege**: Als Ersatz für die pdf.co-Textausgabe dient der Layout-Text von pypdf. Die echte
  pdf.co-Ausgabe kann in Details abweichen.
- **Leistungsabrechnungen**: Die CSV-Fixtures bilden die Spaltenstruktur der pdf.co-Ausgabe
  nach (13 Spalten, Hinweis-Code und -Text in getrennten Spalten). Sie sind aus denselben
  Daten erzeugt wie die PDFs, nicht von pdf.co. Wer die PDFs durch pdf.co schickt, kann das
  gegenprüfen (rund 10 Credits je Abrechnung).

### Stand der Prüfung

| Prüfung | Ergebnis |
|---|---|
| Leistungsabrechnungen: Kopf, Summen, alle Positionen | 3 von 3 fehlerfrei |
| Versichererbrief als Nicht-Abrechnung erkannt | ja |
| Scans ohne Textebene | 21 von 21 |
| Belege, regelbasierter Parser | 117 von 120 Feldern |

Die Abweichungen zeigen Grenzen des regelbasierten Parsers, keine Fehler der Beispiele:

- Steht „Verordnung vom …" oder „Brillenglasbestimmung vom …" vor dem Rechnungsdatum, wird
  jenes Datum als Rechnungsdatum gelesen (Ergotherapie, Optiker).
- „Rechnungsnummer:" wird nicht erkannt, nur „Rechnungs-Nr.".
- Hinweise zur Abrechnung: Der Parser behält nur den Code („156:"), der Text in der
  Nachbarspalte geht verloren (0 von 10 Texten).
- Das Dateinamenschema `NNN_Anbieter_Betrag_Person_PKVB` erkennt `parse_filename` nicht;
  Person und Anbieter bleiben leer.
