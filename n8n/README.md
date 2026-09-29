# n8n-Workflows

Drei Workflows erledigen die Arbeit im Hintergrund. Sie sind aus einer laufenden Instanz
exportiert und bereinigt: Zugänge, Ordner-IDs, Adressen und Instanz-IDs sind durch
Platzhalter ersetzt.

| Datei | Auslöser | Was passiert |
|---|---|---|
| `1-abrechnungen-download.json` | Benachrichtigungs-Mail der Universa (Gmail, minütlich geprüft), täglich 04:00, manuell | Login ins Kundenportal über den [Downloader](../downloader/README.md), PIN aus der 2FA-Mail lesen, neue Dokumente der letzten 4 Tage holen, nach Google Drive legen, dann Workflow 2 aufrufen |
| `2-abrechnung-verarbeiten.json` | neue Datei im Abrechnungs-Ordner (stündlich) oder Aufruf aus Workflow 1 | Leistungsabrechnung an die API (`/settlements/upload`), Datei in „verarbeitet" verschieben; hat die Versicherung Hinweise geschrieben, kommt eine Mail mit der PDF |
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
   | Supabase apikey (Header) | Header Auth | Name `apikey`, Wert: Publishable/Anon-Key des Supabase-Projekts |

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
   | `app-benutzer@example.com`, `APP-PASSWORT` | 2, 3 | Login eines Supabase-Benutzers der App |
   | `du@example.com` | 2 | Empfänger der Hinweis-Mail |
   | `ID-DES-WORKFLOWS-ABRECHNUNG-VERARBEITEN` | 1 | im Knoten „Call …" Workflow 2 auswählen |

Der Gmail-Trigger in Workflow 1 filtert auf Absender und Betreff der Universa-Benachrichtigung
(„uniVersa Kundenportal - Sie haben eine neue Nachricht"). Für andere Versicherer diese beiden
Werte anpassen.

## Zugangsdaten nicht in Knoten speichern

Der Knoten, der den Supabase-Token holt (Workflow 2 „HTTP Request", Workflow 3 „get supabase
user token"), schickt E-Mail und Passwort im Request-Body. Trägt man sie dort direkt ein, stehen
sie in jedem Export und jeder Sicherung des Workflows im Klartext. Besser ist ein Credential vom
Typ **Custom Auth** mit

```json
{ "headers": { "apikey": "<Publishable/Anon-Key>" },
  "body": { "email": "<App-Benutzer>", "password": "<Passwort>" } }
```

und im Knoten Authentication → Generic → Custom Auth; die Body-Felder entfallen dann.

## Die 2FA-Anmeldung

Das Kundenportal schickt bei jeder Anmeldung eine PIN per Mail. Workflow 1 startet den Login
über den Downloader, wartet 30 Sekunden, liest die ungelesenen Mails der Universa, nimmt die
nach dem Login-Start eingegangene, daraus die erste sechsstellige Zahl, und schließt den Login ab. Eine Sitzung wird 5 Minuten lang
wiederverwendet.

Folge: Wer Zugriff auf dieses Postfach und den Downloader hat, kommt ins Kundenportal. Postfach
und Downloader-Token entsprechend schützen.
