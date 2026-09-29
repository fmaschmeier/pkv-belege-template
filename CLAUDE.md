# pkv-belege-template

KI-gestützter Ablauf für PKV-Belege: Scan mit Genius Scan → n8n → Claude → API; Leistungsabrechnungen
der Universa per Portal-Downloader → n8n → API; Abgleich in der Web-App. Überblick in `README.md`,
Ablauf in `docs/ABLAUF.md`, Einrichtung in `docs/EINRICHTUNG.md`.

## Struktur

- `api/` FastAPI (Supabase, pdf.co, Claude), Image wird aus dem Repo-Wurzelverzeichnis gebaut
- `web/` React + Vite + Tailwind; `VITE_*` werden beim Bauen eingesetzt
- `downloader/` Playwright-Dienst für das Kundenportal (Login mit 2FA, Dokumente holen)
- `n8n/` drei Workflows mit Platzhaltern, siehe `n8n/README.md`
- `receipt_parser.py`, `parser.py`, `bank_parser.py` Parser; `api/app/services/receipt_parser.py` ist die Kopie für die API
- `schema.sql` + `migrations/` (in Nummernfolge) = Datenbankstand der laufenden Instanz
- `samples/` synthetische Testdaten, `manifest.json` enthält die Soll-Werte

## Befehle

```bash
pip install -r requirements.txt
python samples/verify_samples.py      # Parser offline gegen die Beispiele prüfen
pip install -r samples/requirements.txt
python samples/generate_samples.py    # Beispiele neu erzeugen, byte-identisch
cd web && npm ci && npm run build     # Typprüfung und Build der Web-App
```

Nach jeder Änderung an einem Parser `verify_samples.py` laufen lassen. Abrechnungen müssen
fehlerfrei bleiben, bei Belegen darf die Trefferzahl nicht sinken.

## Regeln

- **Persönliches ist Konfiguration, nie Code.** Namen, Versicherungsnummern, Adressen, Zugänge und
  Instanz-Adressen kommen aus Umgebungsvariablen, Secret Manager oder n8n-Credentials. Neue
  persönliche Einstellungen als Variable einführen und in `.env.example` sowie
  `docs/EINRICHTUNG.md` eintragen. So kann jede Instanz direkt aus diesem Repo laufen.
- **Keine echten Belege, Namen, Beträge oder Versicherungsnummern ins Repo**, auch nicht in
  Kommentaren, Tests oder Beispielen. Beispiele kommen aus `samples/generate_samples.py`.
- **Keine Standardpasswörter.** Fehlt ein Geheimnis, bricht der Start ab, statt einen Ersatzwert
  zu nehmen.
- **n8n-Workflows nur bereinigt einchecken:** Zugänge als Credentials, Ordner-IDs, Adressen und
  Instanz-IDs als Platzhalter aus `n8n/README.md`.
- Neue Belegarten zuerst im Generator anlegen, mit Soll-Werten im Manifest, dann den Parser anpassen.
- Die Beispieldokumente nutzen einen erfundenen Versicherer. Keine Dokumente erzeugen, die echte
  Versicherer, Praxen oder Personen nachahmen.
