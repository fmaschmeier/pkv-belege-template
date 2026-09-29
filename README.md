# pkv-belege-template

Ein KI-gestützter Ablauf rund um die private Krankenversicherung, vollständig und zum Nachbauen:
Rechnungen mit dem Handy scannen, von Claude auslesen lassen, Leistungsabrechnungen der Universa
automatisch aus dem Kundenportal holen und auslesen, beides abgleichen. Am Ende ist für jeden
Beleg sichtbar, ob er eingereicht, erstattet, gekürzt oder noch offen ist.

Mit 21 synthetischen Belegen und drei passenden Leistungsabrechnungen lassen sich die Parser
sofort ausprobieren, ohne eigene Daten und ohne Konten bei irgendeinem Dienst.

> **Vorlage aus dem echten Einsatz.** Der Code stammt aus dem privaten Alltag und läuft dort
> täglich. Er wird nicht als Produkt gepflegt, aber wer ihn verbessert, verbessert ihn für alle.
>
> **Nicht mit der Universa verbunden.** Parser und Portal-Downloader sind auf die Universa
> Krankenversicherung zugeschnitten. Die Beispieldokumente verwenden einen erfundenen Versicherer.
>
> **Nicht-kommerzielle Lizenz.** Nutzung ohne kommerziellen Zweck ist erlaubt, kommerzielle
> Nutzung nicht (Details unter [Lizenz](#lizenz)). Das ist bewusst keine Open-Source-Lizenz im
> Sinne der OSI.

## So läuft es

```
Papier/PDF ─► Genius Scan (Name mit PKVB) ─► Google Drive ─► n8n: Claude liest aus ─► API ─┐
                                                                                          ├─► Abgleich
Universa-Mail ─► n8n ─► Downloader (Portal-Login, 2FA) ─► Google Drive ─► n8n ─► API ─────┘   in der Web-App
```

Schritt für Schritt in [`docs/ABLAUF.md`](docs/ABLAUF.md).

## Was drin ist

| Pfad | Inhalt |
|---|---|
| [`n8n/`](n8n/README.md) | drei Workflows: Belege erfassen, Abrechnungen aus dem Portal holen, Abrechnungen verarbeiten |
| [`downloader/`](downloader/README.md) | Dienst, der sich per Browser (Playwright) mit 2FA im Kundenportal anmeldet und Dokumente holt |
| [`api/`](api/) | FastAPI: Belege und Abrechnungen speichern, Abgleich, Bank-Import, SEPA-QR |
| [`web/`](web/) | React-Oberfläche: Übersicht, Belege, Abrechnungen, Kontobewegungen, Regeln, Erinnerungen nach § 14 VVG |
| [`receipt_parser.py`](receipt_parser.py), [`parser.py`](parser.py), [`bank_parser.py`](bank_parser.py) | Parser für Belege, Leistungsabrechnungen und Kontoauszüge (CSV im Format des Commerzbank-Exports) |
| [`prompts/beleg-extraktion.md`](prompts/beleg-extraktion.md) | Prompt für Claude |
| [`schema.sql`](schema.sql), [`migrations/`](migrations/) | Datenbank (Supabase/PostgreSQL) |
| [`samples/`](samples/README.md) | synthetische Belege, Scans und Abrechnungen, Soll-Werte, Generator, Prüfskript |
| [`docs/EINRICHTUNG.md`](docs/EINRICHTUNG.md) | Einrichtung aller Teile und Liste aller Einstellungen |

## Schnellstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python samples/verify_samples.py
```

Das Prüfskript lässt beide Parser offline gegen die Beispiele laufen und vergleicht jedes Feld
mit den Soll-Werten aus `samples/manifest.json`. Aktueller Stand: Abrechnungen 3 von 3
fehlerfrei, Belege 117 von 120 Feldern.

Das ganze System einrichten: [`docs/EINRICHTUNG.md`](docs/EINRICHTUNG.md).

## Datenschutz und Sicherheit

- **Gesundheitsdaten verlassen den Rechner.** Claude und pdf.co verarbeiten die Dokumente auf
  ihren Servern, Supabase speichert sie. Das lohnt eine bewusste Entscheidung, besonders bei
  Belegen anderer Personen.
- **Persönliches gehört in die Konfiguration, nicht in den Code.** Namen, Versicherungsnummer,
  Adressen und Zugänge kommen aus Umgebungsvariablen, Secret Manager und n8n-Credentials. Die
  [`.gitignore`](.gitignore) hält `.env`-Dateien, PDFs außerhalb von `samples/` und den lokalen
  pdf.co-Cache aus dem Repo.
- **Die 2FA-Anmeldung ist automatisiert.** n8n liest die PIN aus dem Postfach. Wer Postfach und
  Downloader-Token hat, kommt ins Kundenportal; beides schützen.
- **Kein Standardpasswort.** Die Web-App startet nur mit eigenen Zugangsdaten für den
  Passwortschutz.

## Bekannte Grenzen

- Belege, regelbasierter Parser: „Verordnung vom …" vor dem Rechnungsdatum wird als
  Rechnungsdatum gelesen; „Rechnungsnummer:" wird nicht erkannt, nur „Rechnungs-Nr.".
- Leistungsabrechnungen: Von den Hinweisen der Versicherung bleibt nur der Code („156:"), der
  Text geht verloren.
- Dateinamen im Schema `NNN_Anbieter_Betrag_Person_PKVB.pdf` erkennt `parse_filename` nicht;
  Person und Anbieter kommen dann nur aus dem Beleg selbst.
- Der Downloader hängt am Aufbau des Kundenportals und muss bei Änderungen angepasst werden.

## Lizenz

| Was | Lizenz |
|---|---|
| Code: `*.py`, `api/`, `web/`, `downloader/`, `n8n/*.json`, `schema.sql`, `migrations/` | [PolyForm Noncommercial 1.0.0](LICENSE) |
| Doku, Prompt, Beispieldaten: Markdown-Dateien, `docs/`, `prompts/`, PDFs, Fixtures und `manifest.json` in `samples/` | [CC BY-NC-SA 4.0](LICENSE-DOCS.txt) |

Beide Lizenzen erlauben Nutzung, Änderung und Weitergabe ohne kommerziellen Zweck und
schließen kommerzielle Nutzung aus. Die CC-Lizenz verlangt Namensnennung und Weitergabe unter
gleichen Bedingungen. Der Urhebervermerk steht in [`NOTICE`](NOTICE).
