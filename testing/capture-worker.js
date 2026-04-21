// Twitch Worker + M3U8 Capture Tool
// In DevTools Console einfügen BEVOR die Seite lädt (z.B. über Tampermonkey @run-at document-start)
// oder: Seite öffnen, sofort F12, Console-Tab, einfügen, Enter, dann Seite neu laden

(function () {
    const captured = {
        workers: [],
        m3u8Ads: [],
        m3u8Encodings: []
    };

    // --- 1. Worker-Blob abfangen ---
    const OrigWorker = window.Worker;
    window.Worker = function (url, options) {
        if (typeof url === 'string' && url.startsWith('blob:')) {
            fetch(url)
                .then(r => r.text())
                .then(text => {
                    captured.workers.push({ url, text, ts: Date.now() });
                    console.log('[capture] Worker blob erfasst, Länge:', text.length);
                    _download('twitch-worker-' + Date.now() + '.js', text);
                })
                .catch(err => console.warn('[capture] Worker-Fetch fehlgeschlagen:', err));
        }
        return new OrigWorker(url, options);
    };
    Object.defineProperty(window, 'Worker', { get: () => window.Worker });

    // --- 2. fetch abfangen: M3U8-Dateien mit Ads speichern ---
    const origFetch = window.fetch;
    window.fetch = async function (url, options) {
        const response = await origFetch.apply(this, arguments);
        if (typeof url === 'string') {
            if (url.includes('/channel/hls/') && url.includes('usher')) {
                const clone = response.clone();
                clone.text().then(text => {
                    captured.m3u8Encodings.push({ url, text, ts: Date.now() });
                    console.log('[capture] Encodings-M3U8 erfasst:', url);
                });
            } else if (url.endsWith('.m3u8') || url.includes('.m3u8?')) {
                const clone = response.clone();
                clone.text().then(text => {
                    const hasAd = text.includes('stitched') || text.includes('X-TV-TWITCH-AD');
                    if (hasAd) {
                        captured.m3u8Ads.push({ url, text, ts: Date.now() });
                        console.log('[capture] Ad-M3U8 erfasst:', url);
                        _download('twitch-ad-m3u8-' + Date.now() + '.m3u8', text);
                    }
                });
            }
        }
        return response;
    };

    // --- 3. Alles auf einmal speichern ---
    window.saveCaptured = function () {
        const json = JSON.stringify(captured, null, 2);
        _download('twitch-captured-' + Date.now() + '.json', json);
        console.log('[capture] Gespeichert — Workers:', captured.workers.length,
            '| Ad-M3U8:', captured.m3u8Ads.length,
            '| Encodings:', captured.m3u8Encodings.length);
    };

    function _download(filename, text) {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    console.log('[capture] Hooks installiert. Nach dem Stream: saveCaptured() aufrufen.');
})();
