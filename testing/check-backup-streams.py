#!/usr/bin/env python3
"""
Backup-Stream Verifikation für vaft.js
Prüft ob embed/popout/autoplay Player-Typen noch werbefrei sind.

Usage: python check-backup-streams.py [channel]
"""

import sys
import json
import random
import urllib.request
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CLIENT_ID   = "kimne78kx3ncx6brgo4mv6wki5h1ko"
GQL_HASH    = "ed230aa1e33e07eebb8928504583da78a5173989fadfb1ac94be06a04f3cdbe9"
AD_SIGNALS  = ["stitched", 'CLASS="twitch-stitched-ad"', 'STREAM-SOURCE="Amazon|']
PLAYER_TYPES = ["embed", "popout", "autoplay"]

DE_CHANNELS = [
    "montanablack88", "eliasn97", "trymacs", "handofblood",
    "papaplatte", "knossi", "elotrix", "rewinside",
]


def gql_post(body: dict) -> dict:
    req = urllib.request.Request(
        "https://gql.twitch.tv/gql",
        data=json.dumps(body).encode(),
        headers={
            "Client-ID": CLIENT_ID,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def check_live(channel: str) -> bool:
    try:
        data = gql_post([{
            "operationName": "UseLive",
            "variables": {"channelLogin": channel},
            "extensions": {"persistedQuery": {
                "version": 1,
                "sha256Hash": "639d5f11bfb8bf3053b424d9ef650d04c4ebb7d94711d644afb08fe9a0fad5d9"
            }}
        }])
        user = (data[0].get("data") or {}).get("user") or {}
        return user.get("stream") is not None
    except Exception:
        return False


def get_access_token(channel: str, player_type: str) -> tuple[str, str] | None:
    """Returns (signature, token) or None on failure."""
    platform = "android" if player_type == "autoplay" else "web"
    try:
        data = gql_post({
            "operationName": "PlaybackAccessToken",
            "variables": {
                "isLive": True,
                "login": channel,
                "isVod": False,
                "vodID": "",
                "playerType": player_type,
                "platform": platform,
            },
            "extensions": {"persistedQuery": {"version": 1, "sha256Hash": GQL_HASH}},
        })
        token_data = data.get("data", {}).get("streamPlaybackAccessToken", {})
        sig   = token_data.get("signature")
        token = token_data.get("value")
        if sig and token:
            return sig, token
    except Exception as e:
        print(f"    GQL Fehler: {e}")
    return None


def fetch_text(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    Fetch Fehler: {e}")
        return None


def get_segment_m3u8_url(encodings_m3u8: str) -> str | None:
    """Pick the lowest quality stream URL for quick testing."""
    lines = encodings_m3u8.splitlines()
    urls = [l for l in lines if l.startswith("https://") and ".m3u8" in l]
    return urls[-1] if urls else None  # last = lowest quality


def check_for_ads(text: str) -> tuple[bool, list[str]]:
    found = [s for s in AD_SIGNALS if s in text]
    return bool(found), found


def analyze_player_type(channel: str, player_type: str) -> dict:
    result = {
        "player_type": player_type,
        "token_ok": False,
        "encodings_ok": False,
        "segment_ok": False,
        "encodings_has_ads": False,
        "segment_has_ads": False,
        "ad_signals": [],
        "suppress": "?",
        "status": "FEHLER",
    }

    print(f"  [{player_type}] Access Token holen ...")
    token_info = get_access_token(channel, player_type)
    if not token_info:
        result["status"] = "Token fehlgeschlagen"
        return result
    result["token_ok"] = True
    sig, token = token_info

    # Build usher URL
    p = random.randint(1000000, 9999999)
    usher_url = (
        f"https://usher.ttvnw.net/api/channel/hls/{channel}.m3u8"
        f"?sig={sig}&token={urllib.parse.quote(token)}"
        f"&allow_source=true&allow_spectre=false&p={p}&fast_bread=true"
    )

    print(f"  [{player_type}] Encodings-M3U8 holen ...")
    enc_text = fetch_text(usher_url)
    if not enc_text:
        result["status"] = "Encodings-M3U8 fehlgeschlagen"
        return result
    result["encodings_ok"] = True

    # SUPPRESS check
    for line in enc_text.splitlines():
        if 'DATA-ID="SUPPRESS"' in line:
            result["suppress"] = line.split("VALUE=")[-1].strip('"')

    has_ads, signals = check_for_ads(enc_text)
    result["encodings_has_ads"] = has_ads
    result["ad_signals"].extend(signals)

    # Fetch one segment M3U8
    seg_url = get_segment_m3u8_url(enc_text)
    if not seg_url:
        result["status"] = "Keine Segment-URL gefunden"
        return result

    print(f"  [{player_type}] Segment-M3U8 holen ...")
    seg_text = fetch_text(seg_url)
    if not seg_text:
        result["status"] = "Segment-M3U8 fehlgeschlagen"
        return result
    result["segment_ok"] = True

    has_ads, signals = check_for_ads(seg_text)
    result["segment_has_ads"] = has_ads
    result["ad_signals"].extend([s for s in signals if s not in result["ad_signals"]])

    # Final verdict
    if result["encodings_has_ads"] or result["segment_has_ads"]:
        result["status"] = "ADS GEFUNDEN — nicht werbefrei"
    else:
        result["status"] = "OK — werbefrei"

    return result


def main():
    import urllib.parse  # needed for quote in analyze_player_type

    channel = sys.argv[1] if len(sys.argv) > 1 else None

    if not channel:
        print("[+] Suche live DE-Channel ...")
        for ch in DE_CHANNELS:
            if check_live(ch):
                channel = ch
                print(f"    -> {channel} ist live\n")
                break
        if not channel:
            print("[-] Kein live Channel gefunden. Bitte manuell angeben.")
            sys.exit(1)
    else:
        print(f"[+] Channel: {channel}\n")

    print(f"{'='*56}")
    print(f"  Backup-Stream Check: {channel}")
    print(f"  Prüft ob embed/popout/autoplay noch werbefrei sind")
    print(f"{'='*56}\n")

    results = []
    for pt in PLAYER_TYPES:
        r = analyze_player_type(channel, pt)
        results.append(r)
        print()

    # Summary
    print(f"\n{'='*56}")
    print(f"  ERGEBNIS")
    print(f"{'='*56}")
    print(f"  {'Player-Typ':<12}  {'Token':>6}  {'Suppress':>8}  Ergebnis")
    print(f"  {'-'*50}")
    for r in results:
        token_str = "OK" if r["token_ok"] else "FAIL"
        print(f"  {r['player_type']:<12}  {token_str:>6}  {r['suppress']:>8}  {r['status']}")
        if r["ad_signals"]:
            print(f"  {'':12}  Ad-Signale: {r['ad_signals']}")

    print()
    ad_free = [r for r in results if r["status"].startswith("OK")]
    broken  = [r for r in results if "ADS" in r["status"]]

    if ad_free:
        print(f"  [OK] Werbefreie Backup-Streams: {[r['player_type'] for r in ad_free]}")
        print(f"       vaft.js Kern-Funktion ist INTAKT")
    if broken:
        print(f"  [!] Ads in Backup-Streams: {[r['player_type'] for r in broken]}")
        print(f"      Diese Player-Typen aus BackupPlayerTypes entfernen!")
    if not ad_free and not broken:
        print(f"  [?] Keine auswertbaren Ergebnisse — Channel offline oder Token-Fehler")


if __name__ == "__main__":
    import urllib.parse
    main()
