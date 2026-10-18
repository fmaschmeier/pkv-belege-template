# n8n-Workflows

Drei Workflows erledigen die Arbeit im Hintergrund. Sie sind aus einer laufenden Instanz
exportiert und bereinigt: Zugänge, Ordner-IDs, Adressen und Instanz-IDs sind durch
Platzhalter ersetzt.

| Datei | Auslöser | Was passiert |
|---|---|---|
| `1-abrechnungen-download.json` | Benachrichtigungs-Mail der Universa (Gmail, minütlich geprüft), täglich 04:00, manuell | Login ins Kundenportal über den [Downloader](../downloader/README.md), PIN aus der 2FA-Mail lesen, neue Dokumente der letzten 4 Tage holen, nach Google Drive legen, dann Workflow 2 aufrufen |
| `2-abrechnung-verarbeiten.json` | neue Datei im Abrechnungs-Ordner (stündlich) oder Aufruf aus Workflow 1 | Leistungsabrechnung an die API (`/settlements/upload`); hat die Versicherung Hinweise geschrieben, kommt eine Mail mit der PDF. **Jedes andere Dokument** (Brief, Angebot, Bescheinigung) kommt als PDF per Mail. Danach wandert die Datei in „verarbeitet" |
| `3-belege-erfassen.json` | neue Datei im Genius-Scan-Ordner (alle 10 Minuten) | nur PDFs mit `PKVB` im Namen; Claude liest den Beleg aus, Ergebnis und PDF gehen an die API (`/receipts/import`), Datei in „verarbeitet" verschieben |

## Importieren

1. Workflow 2 zuerst importieren, dann 1 und 3. Workflow 1 ruft Workflow 2 auf.
2. Die Zugänge in n8n anlegen und in den Knoten auswählen:

   | Name im Workflow | n8n-Credential-Typ | Inhalt |
   |---|---|---|
   | Google Drive | Google Drive OAuth2 | Konto mit den Ordnern unten |
   | Gmail | Gmail OAuth2 | Postfach, in dem die Universa-Mails ankommen |
   | Anthropic | Anthropic | API-Schlüssel |
   | Downloader Bearer-Token | Bearer Auth | `BEARER_TOKEN` des Downloaders |
   | Supabase App-Login (Custom Auth) | Custom Auth | JSON mit `apikey`-Header und Login des App-Benutzers, siehe unten |

3. Platzhalter ersetzen:

   | Platzhalter | Workflow | Ersetzen durch |
   |---|---|---|
   | `ORDNER-ID-GENIUS-SCAN-EINGANG` | 3 | Drive-Ordner, in den Genius Scan synchronisiert |
   | `ORDNER-ID-BELEGE-VERARBEITET` | 3 | Ablage für erfasste Belege |
   | `ORDNER-ID-ABRECHNUNGEN-EINGANG` | 1, 2 | Ablage für neu geholte Leistungsabrechnungen |
   | `ORDNER-ID-ABRECHNUNGEN-VERARBEITET` | 1, 2 | Ablage für verarbeitete Abrechnungen; Workflow 1 prüft dort auf Dubletten |
   | `https://DEIN-PROJEKT.supabase.co` | 2, 3 | Supabase-Projekt-URL |
   | `https://DEINE-API.run.app` | 2, 3 | Adresse der API |
   | `https://DEIN-DOWNLOADER.run.app` | 1 | Adresse des Downloaders |
   | `du@example.com` | 2 | Empfänger der Hinweis- und Brief-Mails |
   | `ID-DES-WORKFLOWS-ABRECHNUNG-VERARBEITEN` | 1 | im Knoten „Call …" Workflow 2 auswählen |

Der Gmail-Trigger in Workflow 1 filtert auf Absender und Betreff der Universa-Benachrichtigung
(„uniVersa Kundenportal - Sie haben eine neue Nachricht"). Für andere Versicherer diese beiden
Werte anpassen.

## Der Login der App steht im Credential, nicht im Knoten

Der Knoten, der den Supabase-Token holt (Workflow 2 „HTTP Request", Workflow 3 „get supabase
user token"), schickt nur einen leeren JSON-Body. E-Mail, Passwort und `apikey` steuert das
Credential **Supabase App-Login (Custom Auth)** bei. So stehen sie in keinem Export und keiner
Sicherung des Workflows. Inhalt des Credentials:

```json
{ "headers": { "apikey": "<Publishable/Anon-Key>" },
  "body": { "email": "<App-Benutzer>", "password": "<Passwort>" } }
```

`apikey` ist der Publishable/Anon-Key des Supabase-Projekts; der App-Benutzer ist der aus
[Schritt 1 der Einrichtung](../docs/EINRICHTUNG.md#1-datenbank-supabase).

## Die 2FA-Anmeldung

Das Kundenportal schickt bei jeder Anmeldung eine PIN per Mail. Workflow 1 startet den Login
über den Downloader, wartet 5 Sekunden, liest die ungelesenen Mails der Universa, nimmt die
nach dem Login-Start eingegangene, daraus die erste sechsstellige Zahl, und schließt den Login
ab. Ist die PIN-Mail noch nicht da, schaut er bis zu zwölf Mal im Abstand von 5 Sekunden nach
(rund 60 Sekunden) und bricht dann mit einer Fehlermeldung ab. Die kurzen Abstände sind nötig,
weil die Login-Sitzung nur im Speicher einer Cloud-Run-Instanz liegt und Cloud Run Instanzen
oft schon nach 20 bis 40 Sekunden austauscht; mit 30 Sekunden Wartezeit scheiterte der Login
im Oktober 2026 regelmäßig mit „Session not found“. Eine erfolgreiche Sitzung wird 5 Minuten lang wiederverwendet.

Folge: Wer Zugriff auf dieses Postfach und den Downloader hat, kommt ins Kundenportal. Postfach
und Downloader-Token entsprechend schützen.
