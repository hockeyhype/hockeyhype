// Kör: node worker/test/test.mjs   (inga beroenden)
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { tolkaSchema, tolkaMatch, bevaka } from '../src/index.js';

const fil = n => readFileSync(new URL(`./fixtures/${n}`, import.meta.url), 'utf8');

// --- spelschemat ---
const rader = tolkaSchema(fil('schema.html'));
assert.ok(rader.length > 20, 'schemat ska ge matcher med id');
const boo = rader.find(r => r.id === '1126247');
assert.deepEqual(boo, { id: '1126247', datum: '2026-09-15', hemma: 'Boo HC', borta: 'Viggbyholms IK' });

// --- matchsidan ---
const klar = tolkaMatch(fil('match-klar.html'));
assert.equal(klar.hemma, 'Boo HC');
assert.equal(klar.h, 3); assert.equal(klar.b, 4);
assert.equal(klar.perioder, '1-1, 2-2, 0-0, 0-1');
assert.equal(klar.klar, true);
assert.equal(klar.senast, '2026-09-15 22:37:14');
const live = tolkaMatch(fil('match-live.html'));
assert.equal(live.h, 2); assert.equal(live.b, 1);
assert.equal(live.status, '2nd period'); assert.equal(live.klar, false);
// Publiksiffran efter "Final Score" ska inte läsas som status
const medPublik = tolkaMatch(fil('match-klar.html').replace('>Final Score</div>', '>Final Score</div><div>   Spectators: 28</div>'));
assert.equal(medPublik.status, 'Final Score'); assert.equal(medPublik.klar, true);

// --- en hel runda med låtsas-KV och låtsas-hämtning ---
const kv = new Map();
const env = { LIVE: { get: async (k, t) => kv.has(k) ? JSON.parse(kv.get(k)) : null, put: async (k, v) => kv.set(k, v) } };
const kandidater = JSON.stringify({ matcher: [
  { serie: '21450', tid: '2026-09-15 20:00', hemma: 'Boo HC', borta: 'Viggbyholms IK' },
  { serie: '21450', tid: '2026-09-16 19:00', hemma: 'X', borta: 'Y' },          // i morgon - ska inte röras
] });
let matchsida = 'match-live.html';
const hamtade = [];
const hamtaFn = async url => {
  hamtade.push(url);
  if (url.endsWith('live-kandidater.json')) return kandidater;
  if (url.includes('/Schedule/')) return fil('schema.html');
  if (url.includes('/Game/Events/1126247')) return fil(matchsida);
  throw new Error('oväntad url ' + url);
};
const kl = s => new Date(s); // UTC; 19:10Z = 20:10 svensk vintertid

let r = await bevaka(env, kl('2026-09-15T18:40:00Z'), hamtaFn);   // 20:40 svensk sommartid
assert.equal(r.aktiva, 1);
assert.equal(hamtade.filter(u => u.includes('/Schedule/')).length, 1, 'schemat läses en gång för id');
let lage = JSON.parse(kv.get('live'));
const m = lage.matcher['21450|2026-09-15|Boo HC|Viggbyholms IK'];
assert.equal(m.id, '1126247'); assert.equal(m.h, 2); assert.equal(m.klar, false);

hamtade.length = 0;
matchsida = 'match-klar.html';
r = await bevaka(env, kl('2026-09-15T20:30:00Z'), hamtaFn);
assert.equal(hamtade.filter(u => u.includes('/Schedule/')).length, 0, 'id redan känt - schemat läses inte igen');
assert.deepEqual(r.klara, ['21450']);
lage = JSON.parse(kv.get('live'));
assert.equal(lage.matcher['21450|2026-09-15|Boo HC|Viggbyholms IK'].klar, true);

hamtade.length = 0;
r = await bevaka(env, kl('2026-09-15T20:40:00Z'), hamtaFn);
assert.equal(r.aktiva, 0, 'klar match bevakas inte mer');
assert.equal(hamtade.length, 1, 'bara kandidatlistan hämtas');

// Ingen skrivning till KV när inget ändrats
const fore = kv.get('live');
await bevaka(env, kl('2026-09-15T20:42:00Z'), hamtaFn);
assert.equal(kv.get('live'), fore);

// Städning dagen efter
await bevaka(env, kl('2026-09-16T16:00:00Z'), hamtaFn);
assert.equal(Object.keys(JSON.parse(kv.get('live')).matcher).length, 0);

console.log('alla tester ok');
