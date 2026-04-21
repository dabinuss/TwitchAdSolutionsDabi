# Twitch Ad Capture Tool

Vollautomatisch — kein manuelles Eingreifen nötig.

## Erstmalige Installation

```
install.bat
```

Braucht Python (python.org). Installiert Playwright + Chromium automatisch.

---

## Capture starten

```bat
run.bat                  REM Standard: esl_csgo, 90 Sekunden
run.bat xqc              REM Channel wählen, 90 Sekunden
run.bat xqc 120          REM Channel + Dauer in Sekunden
```

Ein Chromium-Fenster öffnet sich, der Stream startet automatisch.  
Nicht eingeloggt → garantierte Pre-Roll-Werbung.  
Nach Ablauf der Zeit schließt sich der Browser und der Bericht erscheint.

---

## Was wird erfasst

| Datei | Inhalt |
|---|---|
| `captures/worker-[ts].js` | Twitch's HLS-Worker-Code (der wichtigste Teil) |
| `captures/ad-m3u8-[ts].m3u8` | M3U8-Playlist während Werbung mit Ad-Segmenten |
| `captures/encodings-m3u8-[ts].m3u8` | Stream-Auflösungsliste von Twitch |
| `captures/twitch-[ts].har` | Alle Netzwerkanfragen (GQL, Headers, Tokens) |
| `captures/report-[ts].json` | Zusammenfassung + Signifier-Auswertung |

---

## Ergebnis interpretieren

### Alles gut
```
Workers erfasst:    1
Ad-M3U8 erfasst:    3+
Signifier:          ['stitched']
```
→ vaft.js ist noch kompatibel, kein Update nötig.

### Worker nicht erfasst
```
[!] KEIN Worker erfasst
```
→ Twitch hat die Worker-Struktur geändert.  
→ `hookWindowWorker()` in vaft.js prüfen, ggf. Worker-Blob manuell analysieren.

### Keine Ads erfasst
```
[!] KEINE Ad-M3U8 gefunden
```
→ Zwei Möglichkeiten:
- Kein Werbe-Inventar auf dem Channel (anderen Channel probieren)
- `AdSignifier` hat sich geändert (nicht mehr `'stitched'`)
→ Gespeicherte `encodings-m3u8-*.m3u8` öffnen und nach neuen Ad-Tags suchen.

### Unbekannte M3U8-Tags
```
[!] Unbekannte M3U8-Tags: ['#EXT-X-TWITCH-NEWMETHOD']
```
→ Twitch nutzt eine neue Methode.  
→ `vaft.js` → `stripAdSegments()` und `processM3U8()` anpassen.

---

## Was in vaft.js prüfen/anpassen

| Problem | Stelle in vaft.js |
|---|---|
| AdSignifier geändert | Zeile ~13: `scope.AdSignifier = 'stitched'` |
| GQL Hash veraltet | Zeile ~641: `sha256Hash: "ed230a..."` → aus HAR aktualisieren |
| Client-ID veraltet | Zeile ~14: `scope.ClientID` → aus HAR-Headers aktualisieren |
| Worker-Struktur anders | `hookWorkerFetch()` — Worker-JS aus Capture vergleichen |
| React-Player-API anders | `getPlayerAndState()` — Twitch-Seite inspizieren |

### SHA256-Hash aus HAR auslesen
HAR-Datei in VS Code öffnen → nach `PlaybackAccessToken` suchen →  
im Request-Body steht `sha256Hash`.

### Client-ID aus HAR auslesen
HAR-Datei → nach `gql.twitch.tv` suchen → Request-Header `Client-ID`.

---

## Manuelle Fallback-Scripts (optional)

Falls das automatische Tool nicht greift:

| Datei | Zweck |
|---|---|
| `capture-worker.js` | In DevTools Console einfügen → Worker-Blob + M3U8 manuell speichern |
| `check-adsignifier.js` | In DevTools Console einfügen → Signifier-Check ohne vaft.js |
