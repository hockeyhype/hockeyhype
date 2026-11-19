// Service worker for hockeyhype.se - gor sidan installerbar och laddbar utan natverk.
// Natet forst for allt (sa att besokaren alltid far farsk data), cachen bara som reserv nar
// natet inte svarar - t.ex. i en ishall med dalig tackning. Typsnitt och ikoner andras sallan
// och tas fran cachen direkt. Inget skickas nagonstans; cachen ligger bara i besokarens enhet.
const CACHE = 'hockeyhype-v4'; // byt version nar ikoner eller typsnitt andras, sa toms gamla cachen

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(['/', '/fonts/fonts.css'])).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(nycklar => Promise.all(nycklar.filter(n => n !== CACHE).map(n => caches.delete(n))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/')) return; // livedata fran workern - alltid farskt fran natet

  if (url.pathname.startsWith('/fonts/') || url.pathname.startsWith('/ikoner/') || url.pathname.startsWith('/logos/')) {
    e.respondWith(caches.match(req).then(svar => svar || hamtaOchSpara(req)));
    return;
  }
  e.respondWith(hamtaOchSpara(req).catch(() =>
    caches.match(req, { ignoreSearch: true }).then(svar => svar ||
      (req.mode === 'navigate' ? caches.match('/') : Response.error()))));
});

function hamtaOchSpara(req){
  return fetch(req).then(svar => {
    if (svar.ok) {
      const kopia = svar.clone();
      // Spara utan sokdel (datafilerna hamtas med ?v=..., lankar kan ha ?fbclid=...) sa att
      // bara senaste versionen av varje fil ligger kvar
      const url = new URL(req.url);
      caches.open(CACHE).then(c => c.put(url.origin + url.pathname, kopia));
    }
    return svar;
  });
}
