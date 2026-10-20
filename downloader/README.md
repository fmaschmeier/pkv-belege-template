# Downloader für das Universa-Kundenportal

Ein kleiner Dienst, der sich bei `kundenportal.universa.de` mit 2FA anmeldet und die Dokumente
aus dem Postfach herunterlädt, vor allem die Leistungsabrechnungen. Er bietet dafür eine kleine
HTTP-API, die der n8n-Workflow `1-abrechnungen-download` aufruft.

Einen Browser braucht er nicht. Das Portal ist eine Web-App, die alle Daten als JSON unter
`/rest/…` vom Server holt. Der Downloader macht dieselben Aufrufe wie diese Web-App:

| Schritt | Aufruf beim Portal |
|---|---|
| Login-Seite | `GET /login`: Sitzungs-Cookie und CSRF-Token |
| Benutzername und Passwort | `POST /rest/weblogin`, das Portal schickt eine PIN per Mail |
| PIN | dasselbe `POST /rest/weblogin` noch einmal, jetzt mit PIN |
| Dokumentliste | `GET /rest/document/list`, seitenweise, neueste zuerst |
| ein PDF | `GET /rest/document/get/<abrufUrl>.pdf` |

Bis Oktober 2026 hat der Dienst das Portal per Playwright in einem Chromium bedient. Das brach,
als das Portal sein Frontend aktualisierte und der eingebaute Browser zu alt war.

Inoffiziell: Die Universa dokumentiert diese Schnittstelle nicht. Ändert sie sie, muss der Dienst
angepasst werden.

## Endpunkte

Alle außer `/health` verlangen `Authorization: Bearer <BEARER_TOKEN>`.

| Methode und Pfad | Zweck |
|---|---|
| `GET /health` | Lebenszeichen für Cloud Run |
| `POST /login/start` | meldet sich mit Benutzername und Passwort an; das Portal schickt daraufhin eine PIN per Mail. Antwort: `session_id` |
| `POST /login/complete` | `session_id` und `pin` → Anmeldung abgeschlossen. Antwort: eine **neue** `session_id` für die Dokument-Aufrufe |
| `GET /documents?session_id=…&page=0` | eine Seite der Dokumentliste |
| `GET /documents/recent?session_id=…&max_age_days=3` | alle Dokumente der letzten Tage, als Base64 |
| `GET /documents/{id}/download?session_id=…` | ein einzelnes Dokument, `id` aus `/documents` |
| `GET /session/{session_id}`, `DELETE /session/{session_id}` | Sitzung abfragen oder beim Portal abmelden |

Fehlercodes von `POST /login/start`:

| Code | Bedeutung |
|---|---|
| 401 | Das Portal lehnt den Login ab, oder das Bearer-Token ist falsch. `detail` unterscheidet beides. Fehlt der Authorization-Header ganz, antwortet FastAPI 0.109 mit 403 |
| 504 | Das Portal hat nicht rechtzeitig geantwortet |
| 502 | sonstiger Fehler beim Login |

Eine falsche PIN beantwortet `POST /login/complete` mit `success: false`, der Meldung des Portals
und einer `session_id` für einen zweiten Versuch.

## Die Sitzung steckt in der `session_id`

Die Anmeldung beim Portal besteht aus Cookies und dem jeweils letzten CSRF-Token. Der Downloader
hält sie nicht im Speicher, sondern gibt sie verschlüsselt als `session_id` zurück. n8n reicht sie
von Aufruf zu Aufruf weiter. Deshalb ist es egal, welche Cloud-Run-Instanz den nächsten Aufruf
bekommt, und auch ein Neustart dazwischen schadet nicht.

- Verschlüsselt mit Fernet. Der Schlüssel wird per HKDF aus `BEARER_TOKEN` abgeleitet, ein
  weiteres Geheimnis ist nicht nötig. Ein neues Bearer-Token beendet alle offenen Sitzungen.
- Gültig für `SESSION_TIMEOUT_SECONDS` (Standard 300) ab Ausstellung.
- Das Portal tauscht sein Sitzungs-Cookie, sobald es die PIN annimmt. Die `session_id` aus
  `/login/start` taugt deshalb nur für den PIN-Schritt; die Dokumente gibt es nur mit der
  `session_id` aus `/login/complete`.

## Konfiguration

| Variable | Inhalt |
|---|---|
| `BEARER_TOKEN` | frei gewählter, langer Zufallswert; derselbe steht im n8n-Credential „Downloader Bearer-Token" |
| `UNIVERSA_USERNAME`, `UNIVERSA_PASSWORD` | Zugang zum Kundenportal |
| `SESSION_TIMEOUT_SECONDS` | optional, Standard 300 |

Lokal: `.env.example` nach `.env` kopieren, ausfüllen, `docker compose up --build`.

Tests gegen ein nachgebautes Portal, ohne Zugangsdaten:

```bash
pip install -r requirements.txt pytest && pytest -q tests
```

Cloud Run: `cloudbuild.yaml` baut und deployt; die drei Geheimnisse gehören in den Secret
Manager, nicht in Umgebungsvariablen im Klartext.

## Sicherheit

- Der Dienst kennt Benutzername und Passwort des Kundenportals. Wer das Bearer-Token und Zugriff
  auf das Postfach mit den PIN-Mails hat, kommt ins Portal. Token lang und zufällig wählen und nur
  in n8n hinterlegen.
- Eine `session_id` ist ein paar Minuten lang so viel wert wie eine offene Anmeldung, zusammen mit
  dem Bearer-Token. n8n speichert sie 5 Minuten in den Workflow-Daten und in der Ausführung.
- Das Log enthält zu den Login-Schritten nur Status, Feldnamen und Cookie-Namen, keine Werte;
  zur Dokumentliste nur Anzahl und Form der Felder (Ziffern als 9, Buchstaben als a).
