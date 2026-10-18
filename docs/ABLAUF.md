# Der Ablauf

Wer privat krankenversichert ist, zahlt Rechnungen erst selbst, reicht sie ein und bekommt
Wochen später eine Leistungsabrechnung, die mehrere Belege auf einmal erstattet, oft
gekürzt. Bei vielen Belegen im Monat verliert man schnell den Überblick: Was ist bezahlt, was eingereicht, was
erstattet, wo fehlt Geld?

Der Ablauf hält dafür jeden Beleg und jede Abrechnungsposition als Datensatz fest, verbindet
sie miteinander und erledigt das Einsammeln selbst.

```
Papier/PDF ─► Genius Scan (Name mit PKVB) ─► Google Drive ─► n8n: Claude liest aus ─► API ─┐
                                                                                          ├─► Abgleich
Universa-Mail ─► n8n ─► Downloader (Portal-Login, 2FA) ─► Google Drive ─► n8n ─► API ─────┘   in der Web-App
```

## 1. Beleg scannen und benennen

Jede Rechnung wird mit [Genius Scan](https://thegrizzlylabs.com/genius-scan/) auf dem Handy
gescannt. Beim Speichern bekommt die Datei das Kürzel **`PKVB`** in den Namen. Genius Scan
synchronisiert automatisch in einen Google-Drive-Ordner.

Das Kürzel ist der Schalter: Der n8n-Workflow verarbeitet nur PDFs, deren Name `PKVB` enthält.
Andere Scans im selben Ordner bleiben unberührt. Weitere Angaben im Namen, etwa Anbieter, Betrag
und Person (`…_Kinderarzt_48.24_Mila_PKVB.pdf`), helfen nur beim Wiederfinden.

PDF-Rechnungen aus der Mail lassen sich genauso erfassen: in denselben Ordner legen, mit `PKVB` im Namen.

## 2. Beleg erfassen (n8n, `3-belege-erfassen`)

Alle 10 Minuten schaut n8n in den Ordner. Für jede neue `PKVB`-PDF:

1. Datei herunterladen und als Dokument mit dem [Prompt](../prompts/beleg-extraktion.md) an
   Claude schicken. Claude liefert JSON: Belegart (Arzt, Apotheke, Pflege, Hilfsmittel,
   Sonstiges), Anbieter, Rechnungsnummer, Datum, Betrag, behandelte Person, Fälligkeit,
   Zahlungsempfänger, IBAN und Verwendungszweck. Das klappt auch bei schiefen Handy-Scans;
   laut Erfahrung kostet es 2 bis 3 US-Cent je Beleg.
2. JSON und PDF an die API (`POST /receipts/import`). Die API legt den Beleg an, speichert die
   PDF und erkennt Dubletten am SHA-256-Hash der Datei. Steht auf dem Beleg keine Fälligkeit,
   gilt Rechnungsdatum plus 30 Tage.
3. Die Datei wandert in den Ordner „verarbeitet".

Ohne n8n geht es auch regelbasiert mit [`receipt_parser.py`](../receipt_parser.py) über pdf.co.
Das kostet keine KI-Aufrufe, scheitert aber an ungewohnten Formaten und an Scans ohne Textebene.

## 3. Einreichen

Die Belege gehen wie gewohnt an die Versicherung. In der App stehen sie auf „eingereicht".

## 4. Leistungsabrechnung holen (n8n, `1-abrechnungen-download`)

Liegt im Kundenportal ein neues Dokument, schickt die Universa eine Mail „uniVersa Kundenportal -
Sie haben eine neue Nachricht". Darauf reagiert n8n (zusätzlich täglich um 04:00):

1. Der [Downloader](../downloader/README.md) meldet sich per Browser im Portal an. Das Portal
   schickt eine PIN per Mail.
2. n8n wartet 5 Sekunden, liest die PIN aus dieser Mail und schließt den Login ab. Kommt die
   Mail später, schaut n8n alle 5 Sekunden nach, bis zu zwölf Mal (rund 60 Sekunden). Die
   Eile hat einen Grund: Die Anmeldung liegt nur im Speicher der Cloud-Run-Instanz, die den
   Login gemacht hat, und Cloud Run tauscht Instanzen oft schon nach 20 bis 40 Sekunden aus.
   Kommt die PIN später, antwortet der Downloader mit „Session not found“. Eine Sitzung wird
   5 Minuten lang wiederverwendet.
3. Alle Dokumente der letzten 4 Tage werden geholt. Was nicht schon im Ordner „verarbeitet"
   liegt, kommt in den Abrechnungs-Eingang.

## 5. Leistungsabrechnung auslesen (n8n, `2-abrechnung-verarbeiten`)

Für jede PDF im Eingang, die höchstens 23 Stunden alt ist und „Leistungsinformationen" im
Namen trägt:

1. Die API (`POST /settlements/upload`) liest sie mit [`parser.py`](../parser.py), ohne KI.
   **Seite 1**, das Anschreiben: Abrechnungsnummer (`R/26/117`), Datum, Versicherungsnummer und
   der überwiesene Betrag. **Seite 2**, die Einzelaufstellung, wandelt pdf.co in CSV um. Je
   Position stehen darin Belegnummer, Person, Leistungserbringer, Zeitraum, Rechnungsbetrag,
   Tarif, korrigierter und zurückgestellter Betrag, Eigenanteil, Selbstbeteiligung und
   Erstattung. Kosten laut Erfahrung 7 bis 10 pdf.co-Credits je Abrechnung.
2. Die Datei wandert in „verarbeitet".
3. Hat die Versicherung zu einzelnen Positionen Hinweise geschrieben, kommt eine Mail mit der
   PDF im Anhang.

**Alle anderen Dokumente** aus dem Portal (Briefe, Angebote, Bescheinigungen, Hinweise zur
Datensicherheit) liest die App nicht. n8n schickt sie als PDF per Mail und legt sie erst danach
ab. Ohne diese Weiche gingen solche Schreiben unbemerkt in den Ordner „verarbeitet" – samt
Fristen, etwa für befristete Angebote zur Anpassung des Vertrags.

## 6. Abgleich (Web-App)

Die App ordnet jedem eingereichten Beleg eine Abrechnungsposition zu:

| Regel | Wirkung |
|---|---|
| Rechnungsbetrag stimmt auf den Cent überein | Pflicht; verglichen wird der Rechnungsbetrag, nicht die Erstattung |
| Abrechnung liegt nicht vor dem Einreichungsdatum | Pflicht |
| Person stimmt überein | +30 Punkte; nicht Pflicht, weil Belege manchmal unter einem anderen Familienmitglied laufen |
| Zeitraum passt | +20 Punkte |
| Gleichstand | die zeitlich nächste Abrechnung gewinnt |

Danach ist für jeden Beleg sichtbar, ob und wie viel erstattet wurde, und warum weniger:
Selbstbeteiligung, Eigenanteil, Höchstbetrag, Kürzung auf den Regelsatz. Die Beispiele in
[`samples/`](../samples/README.md) enthalten jede dieser Varianten; `samples/manifest.json`
verbindet jeden Beispielbeleg mit seiner Position.

## 7. Geld und Fristen (Web-App)

- **Bank-Import**: Der Kontoauszug als CSV (Format des Commerzbank-Exports) wird eingelesen,
  Erstattungen werden den Abrechnungen zugeordnet, Zahlungen den Belegen.
- **Rechnungen bezahlen**: Aus Zahlungsempfänger und IBAN eines Belegs entsteht ein
  SEPA-QR-Code für die Banking-App.
- **Erinnern**: Nach § 14 Abs. 1 VVG wird die Erstattung fällig, sobald die Versicherung ihre
  Prüfung abgeschlossen hat. Ist sie einen Monat nach Einreichung nicht fertig, kann man nach
  § 14 Abs. 2 VVG eine Abschlagszahlung in Höhe des voraussichtlichen Mindestbetrags verlangen.
  Für Belege, die darüber liegen, entwirft die App eine Erinnerung an die Versicherung.
