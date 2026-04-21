#!/usr/bin/env python3
"""
Twitch Ad Capture Tool
Öffnet automatisch einen Twitch-Channel und erfasst:
  - HLS Worker Blob (Twitch's interner Player-Code)
  - M3U8-Dateien mit Ad-Segmenten
  - HAR-Datei (alle Netzwerkanfragen)
  - Bericht über gefundene/unbekannte Ad-Signifier

Usage:
  python capture.py [channel] [dauer_sekunden]
  python capture.py xqc 90
"""

import asyncio
import sys
import os
import json
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("FEHLER: Playwright nicht installiert.")
    print("Bitte install.bat ausführen.")
    sys.exit(1)

# --- Konfiguration ---
CHANNEL  = sys.argv[1] if len(sys.argv) > 1 else "esl_csgo"
DURATION = int(sys.argv[2]) if len(sys.argv) > 2 else 90
OUT      = Path(__file__).parent / "captures"

KNOWN_M3U8_TAGS = {
    "#EXT-X-STREAM-INF", "#EXT-X-MEDIA", "#EXT-X-VERSION",
    "#EXT-X-TARGETDURATION", "#EXT-X-MEDIA-SEQUENCE",
    "#EXT-X-TWITCH-PREFETCH", "#EXT-X-TWITCH-PREFETCH-DISCONTINUITY",
    "#EXT-X-DISCONTINUITY", "#EXT-X-PROGRAM-DATE-TIME",
    "#EXT-X-SESSION-DATA", "#EXT-X-INDEPENDENT-SEGMENTS",
    "#EXT-X-ENDLIST", "#EXT-X-KEY",
}

# Dieses Script wird vor dem Twitch-Code in den Browser injiziert
INJECT_JS = r"""
(function () {
    window._cap = { workers: [], m3u8Ads: [], m3u8Enc: [], signifiers: {}, unknownTags: {} };

    const SIGNIFIERS = ['stitched', 'X-TV-TWITCH-AD', 'MIDROLL', 'PREROLL'];

    // Worker-Blob abfangen
    const OrigWorker = window.Worker;
    window.Worker = class extends OrigWorker {
        constructor(url, opts) {
            super(url, opts);
            if (typeof url === 'string' && url.startsWith('blob:')) {
                fetch(url).then(r => r.text()).then(text => {
                    window._cap.workers.push({ url, text, ts: Date.now() });
                    console.log('[cap] Worker blob erfasst, Länge:', text.length);
                }).catch(() => {});
            }
        }
    };

    // fetch abfangen → M3U8-Dateien analysieren
    const origFetch = window.fetch;
    window.fetch = async function (url, opts) {
        const resp = await origFetch.apply(this, arguments);
        if (typeof url !== 'string') return resp;

        const isEnc = url.includes('usher.ttvnw.net') || url.includes('/channel/hls/');
        const isSeg = !isEnc && (url.endsWith('.m3u8') || url.includes('.m3u8?'));

        if (isEnc || isSeg) {
            resp.clone().text().then(text => {
                // bekannte Signifier
                SIGNIFIERS.forEach(s => {
                    if (text.includes(s) && !window._cap.signifiers[s])
                        window._cap.signifiers[s] = { url, ts: Date.now() };
                });
                // unbekannte #EXT-X-* Tags
                (text.match(/#EXT-X-[A-Z0-9\-]+/g) || []).forEach(tag => {
                    if (!window._cap.unknownTags[tag] && ![
                        '#EXT-X-STREAM-INF','#EXT-X-MEDIA','#EXT-X-VERSION',
                        '#EXT-X-TARGETDURATION','#EXT-X-MEDIA-SEQUENCE',
                        '#EXT-X-TWITCH-PREFETCH','#EXT-X-TWITCH-PREFETCH-DISCONTINUITY',
                        '#EXT-X-DISCONTINUITY','#EXT-X-PROGRAM-DATE-TIME',
                        '#EXT-X-SESSION-DATA','#EXT-X-INDEPENDENT-SEGMENTS',
                        '#EXT-X-ENDLIST','#EXT-X-KEY'
                    ].includes(tag)) {
                        window._cap.unknownTags[tag] = { url, ts: Date.now() };
                        console.log('[cap] Unbekannter M3U8-Tag:', tag);
                    }
                });

                if (isEnc) {
                    if (window._cap.m3u8Enc.length < 3)
                        window._cap.m3u8Enc.push({ url, text, ts: Date.now() });
                } else if (text.includes('stitched') || text.includes('X-TV-TWITCH-AD')) {
                    window._cap.m3u8Ads.push({ url, text, ts: Date.now() });
                    console.log('[cap] Ad-M3U8 erfasst!');
                }
            }).catch(() => {});
        }
        return resp;
    };

    console.log('[cap] Hooks aktiv');
})();
"""


async def main():
    OUT.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    har_path = str(OUT / f"twitch-{ts}.har")

    print(f"\n{'='*50}")
    print(f"  Twitch Ad Capture")
    print(f"  Channel:  {CHANNEL}")
    print(f"  Dauer:    {DURATION}s")
    print(f"  Ausgabe:  {OUT}")
    print(f"{'='*50}\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        ctx = await browser.new_context(
            record_har_path=har_path,
            viewport={"width": 1280, "height": 720},
        )
        await ctx.add_init_script(INJECT_JS)
        page = await ctx.new_page()

        print(f"[+] Öffne twitch.tv/{CHANNEL} ...")
        await page.goto(f"https://www.twitch.tv/{CHANNEL}", wait_until="domcontentloaded")
        print(f"[+] Warte {DURATION}s (Werbung abwarten) ...\n")

        for i in range(DURATION):
            await asyncio.sleep(1)
            if (i + 1) % 15 == 0 or i == DURATION - 1:
                try:
                    w  = await page.evaluate("window._cap.workers.length")
                    a  = await page.evaluate("window._cap.m3u8Ads.length")
                    sg = await page.evaluate("Object.keys(window._cap.signifiers)")
                    ut = await page.evaluate("Object.keys(window._cap.unknownTags)")
                    print(f"  [{i+1:3d}s] Workers: {w}  Ad-M3U8: {a}  "
                          f"Signifier: {sg}  Unbekannte Tags: {ut}")
                except Exception:
                    print(f"  [{i+1:3d}s] (Seite noch nicht bereit)")

        print("\n[+] Extrahiere Daten ...")
        try:
            cap = await page.evaluate("JSON.parse(JSON.stringify(window._cap))")
        except Exception as e:
            print(f"[-] Fehler beim Extrahieren: {e}")
            cap = {"workers": [], "m3u8Ads": [], "m3u8Enc": [], "signifiers": {}, "unknownTags": {}}

        await ctx.close()
        await browser.close()

    # --- Dateien speichern ---
    saved = []

    for i, w in enumerate(cap.get("workers", [])):
        p = OUT / f"worker-{ts}-{i}.js"
        p.write_text(w["text"], encoding="utf-8")
        saved.append(str(p))
        print(f"[+] Worker gespeichert: {p.name}  ({len(w['text']):,} Zeichen)")

    for i, m in enumerate(cap.get("m3u8Ads", [])):
        p = OUT / f"ad-m3u8-{ts}-{i}.m3u8"
        p.write_text(m["text"], encoding="utf-8")
        saved.append(str(p))
        print(f"[+] Ad-M3U8 gespeichert: {p.name}")

    for i, m in enumerate(cap.get("m3u8Enc", [])):
        p = OUT / f"encodings-m3u8-{ts}-{i}.m3u8"
        p.write_text(m["text"], encoding="utf-8")
        saved.append(str(p))

    report = {
        "timestamp": ts,
        "channel": CHANNEL,
        "duration_s": DURATION,
        "workers_found": len(cap.get("workers", [])),
        "ad_m3u8_found": len(cap.get("m3u8Ads", [])),
        "signifiers": cap.get("signifiers", {}),
        "unknown_tags": cap.get("unknownTags", {}),
        "saved_files": saved,
        "har_file": har_path,
    }
    rp = OUT / f"report-{ts}.json"
    rp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Zusammenfassung ---
    print(f"\n{'='*50}")
    print("  ERGEBNIS")
    print(f"{'='*50}")
    print(f"  Workers erfasst:    {report['workers_found']}")
    print(f"  Ad-M3U8 erfasst:    {report['ad_m3u8_found']}")
    print(f"  Signifier:          {list(report['signifiers'].keys())}")
    print(f"  Unbekannte Tags:    {list(report['unknown_tags'].keys())}")
    print(f"  HAR:                {Path(har_path).name}")
    print(f"  Report:             {rp.name}")
    print(f"  Ausgabe-Ordner:     {OUT}\n")

    # Warnungen
    if report["workers_found"] == 0:
        print("  [!] KEIN Worker erfasst")
        print("      → Worker-Hook in vaft.js könnte veraltet sein\n")
    if report["ad_m3u8_found"] == 0:
        print("  [!] KEINE Ad-M3U8 gefunden")
        print("      → Entweder keine Werbung geschaltet ODER")
        print("        AdSignifier hat sich geändert (aktuell: 'stitched')\n")
    if report["unknown_tags"]:
        print("  [!] Unbekannte M3U8-Tags gefunden:")
        for tag, info in report["unknown_tags"].items():
            print(f"      {tag}  (in: {info['url'][:60]}...)")
        print("      → Könnten neue Twitch Ad-Methoden sein!\n")

    if report["workers_found"] > 0 and report["ad_m3u8_found"] > 0:
        print("  [OK] Alles erfasst — vaft.js scheint noch kompatibel\n")


if __name__ == "__main__":
    asyncio.run(main())
