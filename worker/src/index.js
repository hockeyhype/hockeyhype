// hockeyhype-live: Cloudflare Worker som bevakar pågående matcher.
//
// Varannan minut (cron):
//   1. Läser hockeyhype.se/data/live-kandidater.json (dagens och närmaste dagarnas matcher, skrivs av
//      dagligen.py) och väljer matcherna som pågår eller nyss borde ha börjat/slutat.
//   2. Läser seriens liveöversikt (/StatPage/Live/<serie>/) - ett anrop per serie. Den listar dagens
//      matcher med match-id redan före nedsläpp, och under match ställning, perioder och status.
//      Klara matcher står kvar under "Final Score" i flera timmar.
//   3. Matcher som inte står där (rapporteras inte live) men borde ha börjat: id från spelschemat och
//      ställningen från matchsidan (/Game/Events/<id>).
//   4. Sparar läget i KV ("live") - bara när något ändrats - och väcker GitHub-uppdateringen
//      (repository_dispatch "matchklar") för serier där en match just blivit klar.
//
// GET /api/live svarar med läget som JSON. Sidan hämtar det varje minut när matcher pågår.
// GET /api/match/<id> svarar med hela matchen (händelser, statistik, laguppställning) i samma format
// som data/<säsong>/matcher/<id>.json - för matcher i läget, så att sidan kan visa uppställningen
// före match och händelserna under match.

const SWEHOCKEY = 'https://stats.swehockey.se';
const KANDIDATER = 'https://hockeyhype.se/data/live-kandidater.json';
import { tolkaHelMatch, tolkaLivevy } from './matchdata.js';
export { tolkaHelMatch, tolkaLivevy };

const UA = 'Mozilla/5.0 (compatible; hockeyhype-live; +https://hockeyhype.se/om.html)';
const FORE = 90;             // minuter före nedsläpp vi börjar titta (id:t behövs för laguppställningen)
const EFTER = 4 * 60;        // minuter efter nedsläpp vi slutar (om matchen inte blivit klar)
const MAX_ANROP = 40;        // gratisplanen tillåter 50 anrop till andra sajter per körning
const BEHALL_TIMMAR = 18;    // klara matcher ligger kvar i läget så här länge

// ---------- tid (svensk) ----------
function svenskNu(nu = new Date()) {
  // "YYYY-MM-DD HH:MM" i svensk tid
  const d = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Europe/Stockholm', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(nu);
  return d.replace(',', '');
}
function minuter(tid) {
  // "YYYY-MM-DD HH:MM" -> minuter sedan epoch (bara för jämförelser, tidszonen spelar ingen roll)
  const [d, t = '00:00'] = tid.split(' ');
  const [y, m, dd] = d.split('-').map(Number);
  const [h, mi] = t.split(':').map(Number);
  return Date.UTC(y, m - 1, dd, h, mi) / 60000;
}

// ---------- tolkning av swehockeys sidor ----------
const avkoda = s => s
  .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
  .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
  .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&nbsp;/g, ' ');
const text = s => avkoda(s.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();

// Spelschemat: [{id, datum, hemma, borta}] för rader som har en länk till matchsidan
export function tolkaSchema(html) {
  const ut = [];
  let datum = null;
  for (const [, tr] of html.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/g)) {
    const celler = [...tr.matchAll(/<td[^>]*>([\s\S]*?)<\/td>/g)].map(c => text(c[1]));
    if (!celler.length) continue;
    const d = celler.slice(0, 3).find(c => /^\d{4}-\d{2}-\d{2}/.test(c));
    if (d) datum = d.slice(0, 10);
    const id = (tr.match(/\/Game\/Events\/(\d+)/) || [])[1];
    const match = celler.find(c => c.includes(' - ') && !/^[\d\s\-()]+$/.test(c) && !/^\d+ - \d+/.test(c));
    if (!id || !match || !datum) continue;
    const [hemma, borta] = match.split(' - ').map(s => s.trim());
    ut.push({ id, datum, hemma, borta });
  }
  return ut;
}

// Matchsidan: {hemma, borta, h, b, perioder, status, klar, senast}
export function tolkaMatch(html) {
  const lag = (html.match(/<h2>([^<]+?\s-\s[^<]+)<\/h2>/) || [])[1]; // \s tar även hårt mellanslag
  const info = (html.match(/class="tdInfoArea"[^>]*>([\s\S]*?)<\/td>/) || [])[1] || '';
  const divar = [...info.matchAll(/<div[^>]*>([\s\S]*?)<\/div>/g)].map(d => text(d[1])).filter(Boolean);
  const stalln = divar.find(d => /^\d+\s*-\s*\d+$/.test(d));
  const perioder = (divar.find(d => /^\(.*\)$/.test(d)) || '').replace(/[()]/g, '').trim();
  // Efter ställning och perioder kommer status ("Final Score", "1st period" ...) och, när den förts in,
  // publiksiffran ("Spectators: 28") - den ska inte läsas som status.
  const status = divar.find(d => d !== stalln && !/^\(.*\)$/.test(d) && !/^(spectators|åskådare|publik)/i.test(d)) || '';
  const senast = (html.match(/Last update:\s*([\d-]+ [\d:]+)/) || [])[1] || null;
  if (!lag) return null;
  const [hemma, borta] = text(lag).split(/\s-\s/).map(s => s.trim());
  const [h, b] = stalln ? stalln.split('-').map(s => Number(s.trim())) : [null, null];
  return { hemma, borta, h, b, perioder, status, klar: /final|slut/i.test(status), senast };
}

async function hamta(url) {
  const r = await fetch(url, { headers: { 'User-Agent': UA }, cf: { cacheTtl: 0 } });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.text();
}

const nyckel = m => `${m.serie}|${m.tid.slice(0, 10)}|${m.hemma}|${m.borta}`;

// ---------- en bevakningsrunda ----------
export async function bevaka(env, nu = new Date(), hamtaFn = hamta) {
  const lage = (await env.LIVE.get('live', 'json')) || { matcher: {} };
  const fore = JSON.stringify(lage.matcher);
  const nuSv = svenskNu(nu);
  const nuMin = minuter(nuSv);

  let kandidater = [];
  try {
    kandidater = JSON.parse(await hamtaFn(KANDIDATER)).matcher || [];
  } catch (e) {
    console.log('kandidatlistan gick inte att läsa', e.message);
  }

  // Matcher att titta på just nu. Tid 00:00 betyder att tiden inte är satt - bevaka då hela dagen.
  const aktiva = kandidater.filter(m => {
    const k = lage.matcher[nyckel(m)];
    if (k && k.klar) return false;
    const [dag, tid] = m.tid.split(' ');
    if (!tid || tid === '00:00') return dag === nuSv.slice(0, 10) && nuSv.slice(11) >= '08:00';
    const start = minuter(m.tid);
    return nuMin >= start - FORE && nuMin <= start + EFTER;
  });

  let anrop = 0;
  const klaraSerier = new Set();

  const tioMinuter = Number(nuSv.slice(15, 16)) <= 1; // sista minutsiffran 0 eller 1
  const uppdatera = (m, t) => {
    // t: {id, h, b, perioder, status, klar, senast?} - sparar läget och noterar matcher som just blev klara
    const k = lage.matcher[nyckel(m)] || {};
    const ny = { id: t.id || k.id, serie: m.serie, tid: m.tid, hemma: m.hemma, borta: m.borta };
    if (t.h != null) {
      Object.assign(ny, { h: t.h, b: t.b, perioder: t.perioder, period: t.perioder ? t.perioder.split(',').length : 0,
        status: t.status, klar: t.klar, senast: t.senast || null });
      if (t.klar && !k.klar) klaraSerier.add(m.serie);
      ny.sedd = k.klar === t.klar && k.h === t.h && k.b === t.b ? k.sedd : nuSv;
    }
    lage.matcher[nyckel(m)] = ny;
  };

  // 1) Seriernas liveöversikter: id (redan före nedsläpp), ställning, perioder och status för alla
  //    seriens matcher i ett anrop. Serier med bara matcher utan satt tid läses var tionde minut.
  const sedda = new Set();
  for (const serie of [...new Set(aktiva.map(m => m.serie))]) {
    if (anrop >= MAX_ANROP) break;
    const baraUtanTid = aktiva.filter(m => m.serie === serie).every(m => m.tid.endsWith('00:00'));
    if (baraUtanTid && !tioMinuter) continue;
    try {
      anrop++;
      const rader = tolkaLivevy(await hamtaFn(`${SWEHOCKEY}/StatPage/Live/${serie}/`));
      aktiva.filter(m => m.serie === serie).forEach(m => {
        const r = rader.find(r => r.id && r.hemma === m.hemma && r.borta === m.borta);
        if (!r) return;
        sedda.add(nyckel(m));
        const st = r.text.match(/^(\d+)\s*-\s*(\d+)$/);
        uppdatera(m, { id: r.id, h: st ? Number(st[1]) : null, b: st ? Number(st[2]) : null, perioder: r.perioder,
          status: r.status.replace(/\s*\(\d+:\d+\)\s*$/, ''), klar: r.klar });
      });
    } catch (e) {
      console.log('livevy', serie, e.message);
    }
  }

  // 2) Matcher som inte står i liveöversikten men borde ha börjat: id från spelschemat (var tionde
  //    minut - schemat är stort), sedan matchsidan
  const borjat = m => m.tid.endsWith('00:00') || nuMin >= minuter(m.tid);
  const ejSedda = aktiva.filter(m => !sedda.has(nyckel(m)) && borjat(m));
  const utanId = ejSedda.filter(m => !(lage.matcher[nyckel(m)] || {}).id);
  for (const serie of tioMinuter ? [...new Set(utanId.map(m => m.serie))] : []) {
    if (anrop >= MAX_ANROP) break;
    try {
      anrop++;
      const rader = tolkaSchema(await hamtaFn(`${SWEHOCKEY}/ScheduleAndResults/Schedule/${serie}`));
      utanId.filter(m => m.serie === serie).forEach(m => {
        const r = rader.find(r => r.datum === m.tid.slice(0, 10) && r.hemma === m.hemma && r.borta === m.borta);
        if (r) uppdatera(m, { id: r.id });
      });
    } catch (e) {
      console.log('schema', serie, e.message);
    }
  }
  for (const m of ejSedda) {
    const k = lage.matcher[nyckel(m)];
    if (!k || !k.id || anrop >= MAX_ANROP) continue;
    try {
      anrop++;
      const t = tolkaMatch(await hamtaFn(`${SWEHOCKEY}/Game/Events/${k.id}`));
      if (t && t.h !== null) uppdatera(m, { ...t, id: k.id });
    } catch (e) {
      console.log('match', k.id, e.message);
    }
  }

  // Städa: klara matcher äldre än BEHALL_TIMMAR, och id utan ställning från tidigare dagar
  for (const [n, k] of Object.entries(lage.matcher)) {
    const tid = k.tid || `${n.split('|')[1]} 00:00`;
    if (nuMin - minuter(tid) > BEHALL_TIMMAR * 60) delete lage.matcher[n];
  }

  if (JSON.stringify(lage.matcher) !== fore) {
    lage.uppdaterad = nuSv;
    await env.LIVE.put('live', JSON.stringify(lage));
  }
  if (klaraSerier.size && env.GITHUB_TOKEN) {
    await vackGithub(env, [...klaraSerier]);
  }
  return { aktiva: aktiva.length, anrop, klara: [...klaraSerier] };
}

async function vackGithub(env, serier) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'hockeyhype-live',
    },
    body: JSON.stringify({ event_type: 'matchklar', client_payload: { serier: serier.join(',') } }),
  });
  console.log('GitHub väckt för', serier.join(','), r.status);
}

// ---------- svaret till sidan ----------
async function svaraLive(env) {
  const lage = (await env.LIVE.get('live', 'json')) || { matcher: {} };
  // Matcher med id men utan ställning (inte igång än) följer med, så att sidan kan hämta uppställningen
  const matcher = Object.values(lage.matcher).filter(m => m.id && m.serie);
  return new Response(JSON.stringify({ uppdaterad: lage.uppdaterad || null, matcher }), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'public, max-age=30',
      'Access-Control-Allow-Origin': '*',
    },
  });
}

async function svaraMatch(env, id, ctx) {
  const fel = (status, text) => new Response(text, { status, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  if (!/^\d{5,9}$/.test(id)) return fel(400, 'ogiltigt id');
  const cache = caches.default;
  const cacheNyckel = new Request(`https://hockeyhype.se/api/match/${id}`);
  const sparad = await cache.match(cacheNyckel);
  if (sparad) return sparad;
  // Bara matcher som workern bevakar - workern ska inte bli en allmän genväg till swehockey
  const lage = (await env.LIVE.get('live', 'json')) || { matcher: {} };
  const k = Object.values(lage.matcher).find(m => m.id === id);
  if (!k) return fel(404, 'matchen bevakas inte');
  try {
    const [ev, lu] = await Promise.all([hamta(`${SWEHOCKEY}/Game/Events/${id}`), hamta(`${SWEHOCKEY}/Game/LineUps/${id}`).catch(() => '')]);
    const m = tolkaHelMatch(ev, lu, id, k.serie);
    if (!m.hemma) return fel(404, 'ingen matchsida');
    const svar = new Response(JSON.stringify(m), {
      headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'public, max-age=60', 'Access-Control-Allow-Origin': '*' },
    });
    ctx.waitUntil(cache.put(cacheNyckel, svar.clone()));
    return svar;
  } catch (e) {
    return fel(502, 'swehockey svarar inte');
  }
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(bevaka(env).then(r => console.log('runda', JSON.stringify(r))));
  },
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === '/api/live') return svaraLive(env);
    const mm = url.pathname.match(/^\/api\/match\/([^/]+)$/);
    if (mm) return svaraMatch(env, mm[1], ctx);
    return new Response('Not found', { status: 404 });
  },
};
