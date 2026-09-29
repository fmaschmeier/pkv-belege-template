# Prompt: Beleg mit Claude auslesen

Mit diesem Prompt liest die vollständige App einen Beleg aus. Die PDF geht als
`document`-Block (Base64, `application/pdf`) zusammen mit dem Prompt an die Messages API
von Anthropic, mit `max_tokens: 1024`; das Modell ist konfigurierbar. Die Antwort ist
reines JSON und landet so in der Datenbank.

Derselbe Prompt funktioniert in einem n8n-Workflow: Datei laden, Base64-kodieren, an die
API schicken, JSON aus der Antwort nehmen.

```text
Analysiere dieses PDF einer deutschen Rechnung/eines Belegs und extrahiere folgende Informationen als JSON:

{
  "receipt_type": "arzt|rezept|pflege|hilfsmittel|sonstige",
  "provider_name": "Name des Anbieters/Praxis/Apotheke",
  "invoice_number": "Rechnungsnummer falls vorhanden",
  "invoice_date": "YYYY-MM-DD",
  "invoice_amount": 123.45,
  "insured_person": "Name der behandelten/versicherten Person",
  "description": "Kurze Beschreibung der Leistung",
  "due_date": "YYYY-MM-DD falls angegeben, sonst null",
  "payment_recipient": "Name des Zahlungsempfängers für Überweisung",
  "payment_iban": "IBAN ohne Leerzeichen (z.B. DE89370400440532013000)",
  "payment_reference": "Verwendungszweck falls angegeben"
}

Regeln:
- receipt_type: "arzt" für Ärzte/Therapeuten/Kliniken, "rezept" für Apotheken, "pflege" für Pflegedienste/Lebenshilfe, "hilfsmittel" für Sanitätshäuser/Optiker/Hörgeräte
- invoice_amount: Der Gesamtbetrag als Zahl (z.B. 48.24, nicht "48,24 €")
- payment_recipient: Der Kontoinhaber/Zahlungsempfänger für die Überweisung. Oft identisch mit provider_name, kann aber auch eine privatärztliche Verrechnungsstelle (PVS) o.ä. sein wenn über Abrechnungsstelle
- payment_iban: IBAN ohne Leerzeichen, nur Großbuchstaben und Zahlen. Deutsche IBANs beginnen mit "DE" und haben 22 Zeichen
- payment_reference: Vorgegebener Verwendungszweck falls auf der Rechnung angegeben
- Wenn ein Feld nicht erkennbar ist, setze null
- Antworte NUR mit dem JSON, keine Erklärungen
```

## Ausprobieren

Die Bild-PDFs in [`samples/scans/`](../samples/scans/) haben keine Textebene, wie echte
Handy-Scans. Die Soll-Werte für jeden Beleg stehen in
[`samples/manifest.json`](../samples/manifest.json), darunter auch `payment_recipient` und
`payment_iban`. So lässt sich prüfen, wie gut ein Modell die Felder trifft.

Die IBAN im Prompt ist ein weit verbreitetes Beispiel für das Format. Die IBANs der
Beispielbelege tragen die nicht vergebene Bankleitzahl 000 000 00.
