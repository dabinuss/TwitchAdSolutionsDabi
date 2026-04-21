// AdSignifier-Checker
// Prüft ob der aktuelle AdSignifier ('stitched') in vaft.js noch aktuell ist.
// In DevTools Console einfügen während ein Stream läuft (OHNE vaft.js aktiv).

(function () {
    const KNOWN_SIGNIFIERS = ['stitched', 'X-TV-TWITCH-AD', 'MIDROLL', 'PREROLL'];
    const found = new Map();

    const origFetch = window.fetch;
    window.fetch = async function (url, options) {
        const response = await origFetch.apply(this, arguments);
        if (typeof url === 'string' && (url.endsWith('.m3u8') || url.includes('.m3u8?'))) {
            const clone = response.clone();
            clone.text().then(text => {
                KNOWN_SIGNIFIERS.forEach(sig => {
                    if (text.includes(sig)) {
                        if (!found.has(sig)) {
                            found.set(sig, { url, firstSeen: new Date().toISOString() });
                            console.log(`[signifier] GEFUNDEN: "${sig}" in ${url}`);
                        }
                    }
                });
                // Unbekannte EXT-X Tags loggen (könnten neue Signifier sein)
                const unknownTags = text.match(/#EXT-X-[A-Z\-]+/g) || [];
                unknownTags.forEach(tag => {
                    if (!['#EXT-X-STREAM-INF', '#EXT-X-MEDIA', '#EXT-X-VERSION',
                          '#EXT-X-TARGETDURATION', '#EXT-X-MEDIA-SEQUENCE',
                          '#EXT-X-TWITCH-PREFETCH', '#EXT-X-TWITCH-PREFETCH-DISCONTINUITY',
                          '#EXT-X-DISCONTINUITY', '#EXT-X-PROGRAM-DATE-TIME',
                          '#EXT-X-SESSION-DATA', '#EXT-X-INDEPENDENT-SEGMENTS',
                          '#EXT-X-ENDLIST', '#EXT-X-KEY'].includes(tag)) {
                        console.log(`[signifier] Unbekannter Tag: ${tag} in ${url}`);
                    }
                });
            });
        }
        return response;
    };

    window.getSignifierReport = function () {
        console.table(Object.fromEntries(found));
    };

    console.log('[signifier] Checker aktiv. Nach Werbung: getSignifierReport() aufrufen.');
})();
