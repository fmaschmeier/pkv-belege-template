# Downloader für das Universa-Kundenportal

Ein kleiner Dienst, der sich wie ein Mensch im Browser bei `kundenportal.universa.de`
anmeldet und die Dokumente aus dem Postfach herunterlädt, vor allem die Leistungsabrechnungen.
Er steuert einen echten Chromium über [Playwright](https://playwright.dev/python/) und bietet
dafür eine kleine HTTP-API, die der n8n-Workflow `1-abrechnungen-download` aufruft.

Inoffiziell: Die Universa bietet keine Schnittstelle dafür an. Ändert sie das Portal, muss der
Dienst angepasst werden.

## Endpunkte

Alle außer `/health` verlangen `Authorization: Bearer <BEARER_TOKEN>`.

| Methode und Pfad | Zweck |
|---|---|
| `GET /health` | Lebenszeichen für Cloud Run |
| `POST /login/start` | meldet sich mit Benutzername und Passwort an; das Portal schickt daraufhin eine PIN per Mail. Antwort: `session_id` |
| `POST /login/complete` | `session_id` und `pin` → Anmeldung abgeschlossen |
| `GET /documents?session_id=…` | Liste der Dokumente im Postfach |
| `GET /documents/recent?session_id=…&max_age_days=3` | alle Dokumente der letzten Tage, als Base64 |
| `GET /documents/{index}/download?session_id=…` | ein einzelnes Dokument |
| `GET /session/{session_id}`, `DELETE /session/{session_id}` | Sitzung abfragen oder beenden |

Eine Sitzung läuft nach `SESSION_TIMEOUT_SECONDS` (Standard 300) ab.

Fehlercodes von `POST /login/start`:

| Code | Bedeutung |
|---|---|
| 401 | Das Portal lehnt den Login ab (Fehlermeldung auf der Seite), oder das Bearer-Token ist falsch. `detail` unterscheidet beides. Fehlt der Authorization-Header ganz, antwortet FastAPI 0.109 mit 403 |
| 504 | Das Portal hat nicht rechtzeitig geantwortet, etwa weil Login-Seite oder Formular nicht geladen wurden. Im Oktober 2026 lag das an einem zu alten Browser in Playwright |
| 502 | sonstiger Fehler beim Login |

Die Anmeldung liegt nur im Speicher der Instanz, die `/login/start` bearbeitet hat. Kommt `/login/complete`
bei einer anderen Instanz an, antwortet der Dienst mit 404 („Session not found“). Deshalb gibt n8n die PIN
nach wenigen Sekunden ein, siehe [`n8n/README.md`](../n8n/README.md).

## Konfiguration

| Variable | Inhalt |
|---|---|
| `BEARER_TOKEN` | frei gewählter, langer Zufallswert; derselbe steht im n8n-Credential „Downloader Bearer-Token" |
| `UNIVERSA_USERNAME`, `UNIVERSA_PASSWORD` | Zugang zum Kundenportal |
| `SESSION_TIMEOUT_SECONDS` | optional, Standard 300 |

Lokal: `.env.example` nach `.env` kopieren, ausfüllen, `docker compose up --build`.

Cloud Run: `cloudbuild.yaml` baut und deployt; die drei Geheimnisse gehören in den Secret
Manager, nicht in Umgebungsvariablen im Klartext.

## Sicherheit

- Der Dienst kennt Benutzername und Passwort des Kundenportals. Wer den Bearer-Token und Zugriff
  auf das Postfach mit den PIN-Mails hat, kommt ins Portal. Token lang und zufällig wählen und nur
  in n8n hinterlegen.
- `take_debug_screenshot()` legt auf ausdrücklichen Aufruf einen Screenshot unter `/tmp` im
  Container ab. Solche Bilder zeigen Portalinhalte, also persönliche Daten; nicht dauerhaft
  speichern.
