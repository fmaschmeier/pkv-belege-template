# Einrichtung

Reihenfolge: Datenbank, API, Web-App, Downloader, n8n, Genius Scan. Wer nur die Parser
ausprobieren will, braucht nichts davon, siehe [Schnellstart](../README.md#schnellstart).

Alle persönlichen Angaben (Namen, Versicherungsnummer, Adressen, Zugänge) stehen nur in der
Konfiguration, nie im Code. So lässt sich eine eigene Instanz direkt aus diesem Repo betreiben
und mit `git pull` aktuell halten.

## 1. Datenbank (Supabase)

1. Neues Supabase-Projekt anlegen.
2. Im SQL-Editor ausführen: [`schema.sql`](../schema.sql), danach die Dateien in
   [`migrations/`](../migrations/) in Nummernfolge (`001` bis `005`).
3. Unter Storage zwei **private** Buckets anlegen: `receipts` und `settlements`. Die
   Zugriffsregeln dafür legt das Schema an.
4. Unter Authentication einen Benutzer mit E-Mail und Passwort anlegen. Mit ihm meldet man sich in
   der Web-App an, und n8n holt sich damit einen Token für die API.

Schema und Migrationen ergeben zusammen denselben Stand wie die laufende Instanz, aus der diese
Vorlage stammt (Spalte für Spalte geprüft). Die Views `v_…` nutzt die App nicht; sie sind für
eigene Auswertungen da.

## 2. API (`api/`, FastAPI)

| Variable | Inhalt |
|---|---|
| `SUPABASE_URL` | Projekt-URL |
| `SUPABASE_SERVICE_KEY` | Service-Role- bzw. Secret-Key; die API greift damit an RLS vorbei zu, Benutzer prüft sie selbst über das JWT |
| `SUPABASE_KEY` | Publishable/Anon-Key (Rückfall, falls kein Service-Key gesetzt ist) |
| `SUPABASE_JWT_SECRET` | zum Prüfen der Benutzer-Tokens |
| `PDFCO_API_KEY` | [pdf.co](https://pdf.co), für Leistungsabrechnungen |
| `ANTHROPIC_CLAUDE_API_KEY`, `ANTHROPIC_CLAUDE_MODEL` | für „Neu auslesen" von Belegen in der Web-App |
| `CORS_ORIGINS` | JSON-Liste der Web-Adressen, z. B. `["https://meine-web-app.run.app"]` |
| `INSURED_PERSONS` | Vornamen der versicherten Personen, kommagetrennt |

Vorlage: [`api/.env.example`](../api/.env.example).

- Lokal: `.env` im Repo-Wurzelverzeichnis anlegen, `docker compose up --build`
  ([`docker-compose.yml`](../docker-compose.yml)), API auf Port 8080.
- Cloud Run: aus dem Repo-Wurzelverzeichnis bauen, weil das Image die Parser mitnimmt:
  ```bash
  docker buildx build --platform linux/amd64 -t pkv-api -f api/Dockerfile .
  ```
  Image in eine Registry schieben, `gcloud run deploy`, Variablen als Umgebungsvariablen bzw.
  Secrets setzen.

## 3. Web-App (`web/`, React)

Die `VITE_*`-Werte werden **beim Bauen** in die App geschrieben und als Build-Argumente
übergeben (`docker build --build-arg VITE_API_URL=… web/`):

| Variable | Inhalt |
|---|---|
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_KEY` | Projekt-URL und Publishable/Anon-Key |
| `VITE_API_URL` | Adresse der API |
| `VITE_PERSON_NAMES` | Namen, an denen Banktexte Familienmitglieder erkennen, kommagetrennt |
| `VITE_INSURANCE_NUMBER`, `VITE_RECIPIENT_EMAIL`, `VITE_CC_EMAIL` | für die Erinnerungen an die Versicherung |
| `VITE_SENDER_NAME`, `VITE_SENDER_EMAIL`, `VITE_SENDER_MOBILE` | Absender der Erinnerungen |

Zur **Laufzeit** schützt nginx die Seite zusätzlich per Passwort: `BASIC_AUTH_USER` und
`BASIC_AUTH_PASS` setzen. Ohne diese Werte startet der Container nicht, mit Absicht.

Lokal: `cd web && npm ci && npm run dev`, Werte in `web/.env` (Vorlage
[`web/.env.example`](../web/.env.example)).

## 4. Downloader (`downloader/`)

Siehe [`downloader/README.md`](../downloader/README.md): Bearer-Token festlegen, Zugang zum
Kundenportal im Secret Manager ablegen, mit `cloudbuild.yaml` deployen.

## 5. n8n

Siehe [`n8n/README.md`](../n8n/README.md): drei Workflows importieren, Zugänge anlegen,
Platzhalter ersetzen. Benötigt werden vier Google-Drive-Ordner: Genius-Scan-Eingang, Belege
verarbeitet, Abrechnungen-Eingang, Abrechnungen verarbeitet.

## 6. Genius Scan

In Genius Scan die automatische Synchronisierung mit Google Drive einschalten, Zielordner ist der
Genius-Scan-Eingang aus Schritt 5. Beim Speichern eines Belegs `PKVB` in den Dateinamen schreiben.

## Eigene Instanz aus diesem Repo betreiben

Wer schon eine eigene Fassung betreibt und auf dieses Repo umsteigen will, braucht neben den
bisherigen Werten:

| Neu | Wo | Warum |
|---|---|---|
| `CORS_ORIGINS` | API | Die Web-Adresse steht nicht mehr im Code. Ohne den Wert lehnt die API Aufrufe der Web-App ab |
| `VITE_PERSON_NAMES` | Web (Build-Argument) | Die Namensliste für Banktexte steht nicht mehr im Code |
| `INSURED_PERSONS` | API | Kein vorbelegter Standardwert mehr |
| `BASIC_AUTH_USER`, `BASIC_AUTH_PASS` | Web (Laufzeit) | Kein Standardpasswort mehr; ohne die Werte startet die Web-App nicht |
| Migration `005` | Datenbank | `parsed_params`, falls die Spalte fehlt; die Migration prüft das selbst |
