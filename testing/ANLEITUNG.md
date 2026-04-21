# Test-Anleitung: Twitch Ad-Blocker Analyse

## Ordnerstruktur

```
testing/
├── capture-worker.js       — Speichert Worker-Blob + Ad-M3U8-Dateien automatisch
├── check-adsignifier.js    — Prüft ob bekannte Ad-Signifier noch aktuell sind
└── ANLEITUNG.md            — Diese Datei
```

---

## Schritt 1 — Voraussetzungen

- **Browser:** Chrome oder Firefox
- **Zustand:** vaft.js NICHT aktiv (Tampermonkey deaktivieren oder im normalen Profil testen)
- **Twitch-Account:** Nicht eingeloggt → garantierte Pre-Roll-Ads

---

## Schritt 2 — HAR-Datei aufzeichnen (Netzwerkstruktur)

1. Twitch-Channel öffnen (noch nicht im Stream)
2. `F12` → Reiter **Network**
3. Haken setzen bei **Preserve log**
4. Stream starten, ca. 30 Sekunden warten (bis Werbung durch ist)
5. Rechtsklick im Network-Reiter → **Save all as HAR with content**
6. Datei in `testing/captures/` speichern (Ordner selbst anlegen)

**Was suchen in der HAR:**
- Requests auf `usher.ttvnw.net` → Encodings-M3U8 (Streamauflösungen)
- Requests auf `*.hls.twitchsolutions.com` oder `video-weaver.*.hls.live.tv` → Segment-M3U8 mit Ads
- GQL-Requests auf `gql.twitch.tv` → Access-Token-Anfragen

---

## Schritt 3 — Worker-Blob + Ad-M3U8 automatisch speichern

1. Twitch-Channel öffnen (noch nicht laden)
2. `F12` → **Console**
3. Inhalt von `capture-worker.js` einfügen → Enter
4. Seite **neu laden** (F5) — der Hook ist jetzt aktiv
5. Stream starten, auf Werbung warten
6. Dateien werden automatisch heruntergeladen:
   - `twitch-worker-[ts].js` — Twitch's HLS-Worker (das wichtigste)
   - `twitch-ad-m3u8-[ts].m3u8` — M3U8-Datei während einer Werbung
7. Am Ende in der Console eingeben: `saveCaptured()` → JSON-Zusammenfassung

---

## Schritt 4 — AdSignifier prüfen

Wenn unklar ist ob `stitched` noch der richtige Signifier ist:

1. `F12` → **Console**
2. Inhalt von `check-adsignifier.js` einfügen → Enter
3. Stream öffnen, Werbung abwarten
4. In der Console eingeben: `getSignifierReport()`
5. Die Ausgabe zeigt welche bekannten Tags gefunden wurden und welche unbekannten `#EXT-X-*`-Tags auftauchen

**Wenn ein unbekannter Tag erscheint:** In `vaft.js` Zeile 13 `AdSignifier` anpassen:
```js
scope.AdSignifier = 'stitched'; // ← ggf. hier ändern
```

---

## Schritt 5 — Worker-Blob analysieren

Die gespeicherte `twitch-worker-*.js` enthält Twitch's HLS-Worker-Code.

**Was prüfen:**
- Ist die Funktion zum Fetchen von M3U8 noch gleich aufgebaut?
- Gibt es neue Verschlüsselung oder Obfuskation?
- Werden neue Worker-Message-Keys verwendet?

Relevante Stellen in `vaft.js` die davon abhängen:
- `hookWorkerFetch()` — Hook-Punkt im Worker
- `getWasmWorkerJs()` — Lädt den Worker-Code per XHR
- Worker-Blob-String ab Zeile ~122 — Injizierter Code

---

## Zukünftige Updates (Wiederholung)

Twitch ändert seinen Player ca. alle paar Wochen. Folgender Ablauf:

1. **Testen:** Script via Tampermonkey laden, Stream öffnen, Console beobachten
   - `hookWorkerFetch (vaft)` muss erscheinen → Worker-Hook greift
   - `Blocking ads (embed)` oder ähnlich → Ad-Blocking aktiv
   - Falls nichts → Schritt 2–4 oben wiederholen

2. **Häufigste Änderungen die Fixes brauchen:**
   | Was sich ändert | Wo in vaft.js anpassen |
   |---|---|
   | AdSignifier (nicht mehr `stitched`) | Zeile 13: `scope.AdSignifier` |
   | Access-Token GQL Hash | Zeile 641: `sha256Hash` |
   | Twitch Client-ID | Zeile 14: `scope.ClientID` |
   | Worker-Struktur geändert | `hookWorkerFetch()` überarbeiten |
   | React-Player-API geändert | `getPlayerAndState()` anpassen |

3. **SHA256-Hash aktualisieren:**
   In der HAR-Datei nach `PlaybackAccessToken` suchen → Request-Body enthält den aktuellen Hash

4. **Client-ID aktualisieren:**
   In der HAR-Datei nach `gql.twitch.tv` suchen → Request-Header `Client-ID`

---

## Schnell-Referenz: Console-Befehle während Test

```js
// Aktuellen Stand prüfen (während vaft.js aktiv):
window.twitchAdSolutionsVersion  // → sollte 24 sein

// Ads simulieren (zum Testen ohne echte Werbung):
simulateAds(1)   // Backup-Player aktivieren
simulateAds(0)   // Zurücksetzen

// Player manuell neu laden:
reloadTwitchPlayer()

// Alle erfassten Daten speichern (nach capture-worker.js):
saveCaptured()

// Signifier-Report (nach check-adsignifier.js):
getSignifierReport()
```
