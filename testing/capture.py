#!/usr/bin/env python3
"""
Twitch Ad Capture Tool
Usage:
  python capture.py [channel] [dauer_sekunden]   -- normaler Capture
  python capture.py --hunt [dauer_pro_channel]   -- Preroll-Hunt: mehrere Channels bis Ad gefunden
"""

import asyncio
import sys
import os
import re
import json
import urllib.request
from datetime import datetime
from pathlib import Path

# Windows-Terminal: UTF-8 erzwingen
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("FEHLER: Playwright nicht installiert. Bitte install.bat ausfuehren.")
    sys.exit(1)

HUNT_MODE = len(sys.argv) > 1 and sys.argv[1] == '--hunt'
CHANNEL   = None if HUNT_MODE or len(sys.argv) < 2 else sys.argv[1]
DURATION  = int(sys.argv[2]) if len(sys.argv) > 2 else (45 if HUNT_MODE else 90)
OUT       = Path(__file__).parent / "captures"

# Deutschsprachige Channels — der Reihe nach probiert bis einer live ist
DE_CHANNELS = [
    "montanablack88", "eliasn97", "trymacs", "handofblood",
    "papaplatte", "knossi", "elotrix", "rewinside",
    "dner", "eligella", "ungespielt", "celebrimbor__",
]

# In den Browser injiziert (vor Twitch-Code) — nur Worker-Blob abfangen
INJECT_JS = r"""
(function () {
    window._cap = { workerUrls: [], workerTexts: [] };
    const Orig = window.Worker;
    window.Worker = function (url, opts) {
        const w = new Orig(url, opts);
        if (typeof url === 'string' && url.startsWith('blob:')) {
            window._cap.workerUrls.push(url);
            fetch(url)
                .then(r => r.text())
                .then(t => { window._cap.workerTexts.push(t); })
                .catch(() => {});
        }
        return w;
    };
    window.Worker.prototype = Orig.prototype;
    console.log('[cap] Worker-Hook aktiv');
})();
"""


def fetch_url(url: str) -> str:
    """Einfacher HTTP-GET ohne externe Deps."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def check_live_via_api(channel: str) -> bool:
    """Schnellcheck ob ein Channel live ist (kein Auth nötig)."""
    try:
        req = urllib.request.Request(
            "https://gql.twitch.tv/gql",
            data=json.dumps([{
                "operationName": "UseLive",
                "variables": {"channelLogin": channel},
                "extensions": {"persistedQuery": {
                    "version": 1,
                    "sha256Hash": "639d5f11bfb8bf3053b424d9ef650d04c4ebb7d94711d644afb08fe9a0fad5d9"
                }}
            }]).encode(),
            headers={
                "Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            user = (data[0].get("data") or {}).get("user") or {}
            return user.get("stream") is not None
    except Exception:
        return False  # Im Zweifel trotzdem versuchen


async def main(force_channel=None, force_duration=None):
    OUT.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    duration = force_duration if force_duration is not None else DURATION

    # Channel bestimmen — falls nicht angegeben: ersten live DE-Channel finden
    channel = force_channel or CHANNEL
    if not channel:
        print("\n[+] Suche live DE-Channel ...")
        for ch in DE_CHANNELS:
            live = check_live_via_api(ch)
            status = "LIVE" if live else "offline"
            print(f"    {ch:25s} {status}")
            if live:
                channel = ch
                break
        if not channel:
            print("\n[-] Kein DE-Channel gerade live. Bitte spaeter erneut versuchen")
            print("    oder manuell: run.bat [channel]")
            return

    print(f"\n{'='*52}")
    print(f"  Twitch Ad Capture Tool")
    print(f"  Channel : {channel}")
    print(f"  Dauer   : {duration}s")
    print(f"  Ausgabe : {OUT}")
    print(f"{'='*52}\n")

    har_path = str(OUT / f"twitch-{ts}.har")

    # Gesammelte Daten
    m3u8_enc  = []   # Encodings-M3U8 (Auflösungsliste)
    m3u8_ads  = []   # Segment-M3U8 mit Ad-Signifier
    m3u8_all  = []   # alle Segment-M3U8 (max 5 unique)
    signifiers_found = {}
    unknown_tags     = {}

    KNOWN_SIGNIFIERS = ["stitched", "X-TV-TWITCH-AD", "MIDROLL", "PREROLL"]
    KNOWN_TAGS = {
        "#EXT-X-STREAM-INF", "#EXT-X-MEDIA", "#EXT-X-VERSION",
        "#EXT-X-TARGETDURATION", "#EXT-X-MEDIA-SEQUENCE",
        "#EXT-X-TWITCH-PREFETCH", "#EXT-X-TWITCH-PREFETCH-DISCONTINUITY",
        "#EXT-X-DISCONTINUITY", "#EXT-X-PROGRAM-DATE-TIME",
        "#EXT-X-SESSION-DATA", "#EXT-X-INDEPENDENT-SEGMENTS",
        "#EXT-X-ENDLIST", "#EXT-X-KEY",
        "#EXT-X-DATERANGE", "#EXT-X-START",
        "#EXT-X-TWITCH-LIVE-SEQUENCE", "#EXT-X-TWITCH-ELAPSED-SECS",
        "#EXT-X-TWITCH-TOTAL-SECS", "#EXT-X-PLAYLIST-TYPE",
    }
    seen_m3u8_urls = set()
    stream_active  = False

    is_vod = False

    async def on_response(response):
        nonlocal stream_active, is_vod
        url = response.url
        try:
            if "usher.ttvnw.net" in url or "/channel/hls/" in url:
                text = await response.text()
                if "#EXT-X" in text or "#EXTM3U" in text:
                    # VOD-Erkennung: cloudfront_vod + s3 origin = kein Live-Stream
                    if 'CLUSTER",VALUE="cloudfront_vod' in text and 'ORIGIN",VALUE="s3' in text:
                        is_vod = True
                        print(f"  [VOD] Kanal offline — Twitch zeigt letztes VOD ({channel})")
                        return
                    m3u8_enc.append({"url": url, "text": text})
                    stream_active = True
                return

            if (".m3u8" in url) and url not in seen_m3u8_urls:
                seen_m3u8_urls.add(url)
                text = await response.text()
                if not text.strip():
                    return

                # Signifier prüfen
                for sig in KNOWN_SIGNIFIERS:
                    if sig in text and sig not in signifiers_found:
                        signifiers_found[sig] = url
                        print(f"  [!] Signifier gefunden: '{sig}'")

                # Unbekannte Tags
                for tag in re.findall(r"#EXT-X-[A-Z0-9\-]+", text):
                    if tag not in KNOWN_TAGS and tag not in unknown_tags:
                        unknown_tags[tag] = url
                        print(f"  [?] Unbekannter Tag: {tag}")

                is_ad = any(s in text for s in ["stitched", "X-TV-TWITCH-AD"])
                if is_ad:
                    m3u8_ads.append({"url": url, "text": text})
                    print(f"  [AD] Ad-M3U8 erfasst!")
                    stream_active = True

                if len(m3u8_all) < 5:
                    m3u8_all.append({"url": url, "text": text})
                    stream_active = True
        except Exception:
            pass

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        ctx = await browser.new_context(
            record_har_path=har_path,
            viewport={"width": 1280, "height": 720},
        )
        await ctx.add_init_script(INJECT_JS)
        page = await ctx.new_page()
        page.on("response", on_response)

        print(f"[+] Oeffne twitch.tv/{channel} ...")
        try:
            await page.goto(
                f"https://www.twitch.tv/{channel}",
                wait_until="domcontentloaded",
                timeout=30000,
            )
        except Exception as e:
            print(f"[-] Seitenaufruf fehlgeschlagen: {e}")

        print(f"[+] Warte {duration}s (Werbung abwarten) ...\n")
        for i in range(duration):
            await asyncio.sleep(1)
            # Früh abbrechen wenn VOD erkannt
            if is_vod and i >= 5:
                print(f"  [!] VOD erkannt — Capture abgebrochen")
                break
            if (i + 1) % 15 == 0 or i == duration - 1:
                try:
                    n_workers = await page.evaluate("window._cap.workerUrls.length")
                except Exception:
                    n_workers = "?"
                print(
                    f"  [{i+1:3d}s]  Workers: {n_workers}"
                    f"  Enc-M3U8: {len(m3u8_enc)}"
                    f"  Ad-M3U8: {len(m3u8_ads)}"
                    f"  Signifier: {list(signifiers_found.keys())}"
                    f"  Stream aktiv: {stream_active}"
                )

        # Worker-Blobs aus dem Browser holen
        print("\n[+] Extrahiere Worker-Daten ...")
        try:
            worker_texts = await page.evaluate("window._cap.workerTexts")
            worker_urls  = await page.evaluate("window._cap.workerUrls")
        except Exception:
            worker_texts, worker_urls = [], []

        await ctx.close()
        await browser.close()

    # --- Dateien speichern ---
    saved = []

    # Worker-Blobs speichern + importScripts-URL auflösen
    real_worker_urls = set()
    for i, text in enumerate(worker_texts):
        p = OUT / f"worker-blob-{ts}-{i}.js"
        p.write_text(text, encoding="utf-8")
        saved.append(str(p))
        print(f"[+] Worker-Blob gespeichert: {p.name}  ({len(text):,} Zeichen)")

        # importScripts-URL extrahieren und herunterladen
        matches = re.findall(r"importScripts\(['\"]([^'\"]+)['\"]\)", text)
        real_worker_urls.update(matches)

    for url in real_worker_urls:
        print(f"[+] Lade echten Worker-Code: {url}")
        fname = re.sub(r"[^a-zA-Z0-9.\-_]", "_", url.split("/")[-1])
        p = OUT / f"worker-real-{ts}-{fname}"
        try:
            content = fetch_url(url)
            p.write_text(content, encoding="utf-8")
            saved.append(str(p))
            print(f"    -> {p.name}  ({len(content):,} Zeichen)")
        except Exception as e:
            print(f"    -> FEHLER: {e}")

    # Encodings-M3U8
    for i, m in enumerate(m3u8_enc[:3]):
        p = OUT / f"encodings-m3u8-{ts}-{i}.m3u8"
        p.write_text(m["text"], encoding="utf-8")
        saved.append(str(p))

    # Ad-M3U8
    for i, m in enumerate(m3u8_ads):
        p = OUT / f"ad-m3u8-{ts}-{i}.m3u8"
        p.write_text(m["text"], encoding="utf-8")
        saved.append(str(p))
        print(f"[+] Ad-M3U8 gespeichert: {p.name}")

    # Normale M3U8 (falls keine Ads)
    if not m3u8_ads:
        for i, m in enumerate(m3u8_all):
            p = OUT / f"segment-m3u8-{ts}-{i}.m3u8"
            p.write_text(m["text"], encoding="utf-8")
            saved.append(str(p))

    # Report
    report = {
        "timestamp": ts,
        "channel": channel,
        "duration_s": duration,
        "stream_was_active": stream_active,
        "was_vod": is_vod,
        "workers_blob_found": len(worker_texts),
        "workers_real_urls": list(real_worker_urls),
        "enc_m3u8_found": len(m3u8_enc),
        "ad_m3u8_found": len(m3u8_ads),
        "signifiers_found": signifiers_found,
        "unknown_tags": unknown_tags,
        "saved_files": saved,
        "har_file": har_path,
    }
    rp = OUT / f"report-{ts}.json"
    rp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- Zusammenfassung ---
    print(f"\n{'='*52}")
    print("  ERGEBNIS")
    print(f"{'='*52}")
    print(f"  Stream aktiv:        {stream_active}")
    print(f"  Worker-Blobs:        {report['workers_blob_found']}")
    print(f"  Echter Worker-Code:  {len(real_worker_urls)} URL(s)")
    print(f"  Encodings-M3U8:      {report['enc_m3u8_found']}")
    print(f"  Ad-M3U8:             {report['ad_m3u8_found']}")
    print(f"  Signifier:           {list(signifiers_found.keys())}")
    print(f"  Unbekannte Tags:     {list(unknown_tags.keys())}")
    print(f"  Ausgabe:             {OUT}")
    print()

    if is_vod:
        print("  [!] Kanal war offline — Twitch hat VOD gezeigt, kein Capture")
        print("      Tipp: run.bat ohne Channel aufrufen (sucht live DE-Channel)")
    elif not stream_active:
        print("  [!] Kein Stream gefunden — Channel offline?")
        print("      Tipp: run.bat ohne Channel aufrufen")
    if report["workers_blob_found"] == 0:
        print("  [!] Kein Worker erfasst — Worker-Hook in vaft.js pruefen")
    if stream_active and report["ad_m3u8_found"] == 0:
        print("  [!] Keine Ad-M3U8 — kein Werbe-Inventar oder AdSignifier veraendert")
    if unknown_tags:
        print("  [!] Unbekannte Tags -> neue Twitch-Methode moeglich!")
    if stream_active and report["workers_blob_found"] > 0 and not unknown_tags:
        print("  [OK] vaft.js scheint noch kompatibel")


async def hunt():
    """Preroll-Hunt: probiert DE-Channels nacheinander bis eine Ad-M3U8 gefunden wird."""
    per_channel = DURATION  # z.B. 45s pro Channel
    print(f"\n{'='*52}")
    print(f"  PREROLL-HUNT  ({per_channel}s pro Channel)")
    print(f"{'='*52}\n")

    candidates = []
    print("[+] Prüfe welche Channels live sind ...")
    for ch in DE_CHANNELS:
        live = check_live_via_api(ch)
        status = "LIVE" if live else "offline"
        print(f"    {ch:25s} {status}")
        if live:
            candidates.append(ch)

    if not candidates:
        print("\n[-] Keine live Channels gefunden.")
        return

    print(f"\n[+] {len(candidates)} live Channel(s). Starte Hunt ...\n")

    ads_before = sorted(OUT.glob("ad-m3u8-*.m3u8"))

    for ch in candidates:
        print(f"\n{'─'*52}")
        print(f"  Teste: {ch}  ({per_channel}s)")
        print(f"{'─'*52}")
        await main(force_channel=ch, force_duration=per_channel)
        ads_after = sorted(OUT.glob("ad-m3u8-*.m3u8"))
        new_ads = [f for f in ads_after if f not in ads_before]
        if new_ads:
            print(f"\n[HUNT OK] Preroll gefunden bei '{ch}'!")
            for f in new_ads:
                print(f"         -> {f.name}")
            print("[HUNT] Hunt beendet.")
            return
        ads_before = ads_after
        print(f"[HUNT] Kein Preroll bei {ch}, naechster ...")

    print("\n[HUNT] Kein Preroll gefunden. Spaeter erneut versuchen.")


if __name__ == "__main__":
    if HUNT_MODE:
        asyncio.run(hunt())
    else:
        asyncio.run(main())
