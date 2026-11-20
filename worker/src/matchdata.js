// Matchsidan i workern: samma tolkning som matchdata.py (håll dem i takt), men för matcher som inte
// är klara än. Ger samma format som data/<säsong>/matcher/<id>.json, så att sidan kan visa
// laguppställningen före match och händelserna under match. Se matchdata.py för formatet.

const avkoda = s => String(s || '')
  .replace(/&#x([0-9a-f]+);/gi, (_, h) => String.fromCodePoint(parseInt(h, 16)))
  .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
  .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')
  .replace(/&#39;|&apos;/g, "'").replace(/&nbsp;/g, ' ');
// som swehockey.clean
export const rensa = s => avkoda(String(s || '').replace(/<br\s*\/?>/g, ' ').replace(/<[^>]+>/g, ''))
  .replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();

function spelare(s) {
  const m = rensa(s).match(/^\s*(\d+)\.\s*(.+?)\s*$/);
  return m ? { nr: Number(m[1]), namn: m[2] } : null;
}
const tal = s => (String(s || '').match(/\d+/g) || []).map(Number);
const alla = (re, s) => [...String(s).matchAll(re)];
const PUBLIK = /^(spectators|åskådare|publik)/i;

export function tolkaHandelser(t, id = null) {
  t = t.replace(/\u00a0/g, ' ');
  const h2 = t.match(/<h2>([^<]+?)\s-\s([^<]+)<\/h2>/);
  const [hemma, borta] = h2 ? [avkoda(h2[1]).trim(), avkoda(h2[2]).trim()] : ['', ''];
  const fore = t.includes('Actions</h2>') ? t.slice(0, t.indexOf('Actions</h2>')) : t;
  const h3 = alla(/<h3[^>]*>(.*?)<\/h3>/gs, fore).map(m => rensa(m[1]));
  let datum = '', tid = '', arena = '';
  if (h3.length) {
    const m = h3[0].match(/^(\d{4}-\d{2}-\d{2})\s*(\d{1,2}:\d{2})?/);
    if (m) { datum = m[1]; tid = m[2] || ''; }
    if (h3.length >= 3) arena = h3[2];
  }

  const info = t.match(/class="tdInfoArea"[^>]*>(.*?)<\/td>/s);
  const divar = info ? alla(/<div[^>]*>(.*?)<\/div>/gs, info[1]).map(m => rensa(m[1])) : [];
  const stalln = divar.find(d => /^\d+\s*-\s*\d+$/.test(d)) || null;
  const [h, b] = stalln ? tal(stalln) : [null, null];
  const perStr = divar.find(d => /^\(.*\)$/.test(d)) || '';
  const perioder = alla(/(\d+)-(\d+)/g, perStr).map(m => [Number(m[1]), Number(m[2])]);
  const pd = divar.find(d => PUBLIK.test(d) && tal(d).length);
  const publik = pd ? tal(pd)[0] : null;
  const status = divar.find(d => d !== stalln && !/^\(.*\)$/.test(d) && !PUBLIK.test(d)) || '';

  const lag = { h: {}, b: {} };
  for (const [namn, nyckel] of [['Shots', 'skott'], ['Saves', 'raddningar'], ['PIM', 'pim'], ['PP', 'pp']]) {
    const re = new RegExp('<td class="tdOdd ?">\\s*' + namn + '\\s*</td>\\s*<td class="tdOdd ?">\\s*<strong>(.*?)</strong>\\s*</td>\\s*'
      + '<td class="tdOdd leftPad">(.*?)</td>', 'gs');
    alla(re, t).slice(0, 2).forEach((m, i) => {
      const sida = i ? 'b' : 'h';
      const varde = rensa(m[1]), inom = rensa(m[2]);
      if (nyckel === 'skott' || nyckel === 'raddningar') lag[sida][nyckel] = tal(inom);
      else if (nyckel === 'pim') lag[sida].pim = tal(varde).length ? tal(varde)[0] : 0;
      else { lag[sida].pp = varde; lag[sida].pptid = inom.replace(/^[()\s]+|[()\s]+$/g, ''); }
    });
  }

  const senast = t.match(/Last update:\s*([\d-]+ [\d:]+)/);
  const res = { v: 2, id: id ? String(id) : null, datum, tid, arena, publik, hemma, borta, h, b, perioder, status,
    klar: status.toLowerCase() === 'final score', senast: senast ? senast[1] : null, lag };

  const del = t.includes('Actions</h2>') ? t.slice(t.indexOf('Actions</h2>')) : '';
  const malvakter = [], handelser = [];
  let period = '';
  for (const [, tr] of alla(/<tr[^>]*>(.*?)<\/tr>/gs, del)) {
    const rubrik = tr.match(/<h3>(.*?)<\/h3>/s);
    if (rubrik) { period = rensa(rubrik[1]); continue; }
    const celler = alla(/<td[^>]*?(?:\/>|>(.*?)<\/td>)/gs, tr).map(m => m[1] || '');
    if (period === 'Goalkeeper Summary') {
      const c = celler.filter(x => rensa(x));
      if (c.length >= 3) {
        const sp = spelare(c[1]);
        const rs = rensa(c[2]).match(/\((\d+)\/(\d+)\)/);
        if (sp) malvakter.push({ kort: rensa(c[0]), ...sp, rdd: rs ? Number(rs[1]) : null, skott: rs ? Number(rs[2]) : null });
      }
      continue;
    }
    if (celler.length < 4 || !/^\d{1,3}:\d{2}$/.test(rensa(celler[0]))) continue;
    const tid_ = rensa(celler[0]), typ = rensa(celler[1]), kort = rensa(celler[2]);
    let rest = celler[3] || '', orsakCell = celler.length > 4 ? celler[4] : '';
    const i = rest.indexOf('<td');
    if (i >= 0) { orsakCell = rest.slice(i + 3).replace(/^[^>]*>/, ''); rest = rest.slice(0, i); }
    const e = { period, tid: tid_, kort };
    const mal = typ.match(/^(\d+-\d+)\s*\(([^)]*)\)$/);
    if (mal) {
      const huvud = rest.split(/<span|<div/)[0];
      const assist = alla(/<div[^>]*>(.*?)<\/div>/gs, rest).map(m => spelare(m[1])).filter(Boolean);
      const malnr = rest.match(/title="[^"]*goals[^"]*"\s*>\s*\((\d+)\)/s);
      Object.assign(e, { typ: 'mal', stallning: mal[1], lage: mal[2], spelare: spelare(huvud),
        malnr: malnr ? Number(malnr[1]) : null, assist });
    } else if (/^\d+ min$/.test(typ)) {
      Object.assign(e, { typ: 'utv', min: Number(typ.split(' ')[0]), spelare: spelare(rest),
        orsak: rensa(orsakCell.split(/<br\s*\/?>/)[0]) });
    } else if (typ === 'GK In' || typ === 'GK Out') {
      Object.assign(e, { typ: typ === 'GK In' ? 'mv_in' : 'mv_ut', spelare: spelare(rest) });
    } else if (typ === 'TO') {
      e.typ = 'timeout';
    } else {
      Object.assign(e, { typ: 'annat', text: [typ, rensa(rest), rensa(orsakCell)].filter(Boolean).join(' ') });
    }
    handelser.push(e);
  }
  res.handelser = handelser.reverse();
  res.malvakter = malvakter;
  return res;
}

const POS_ORDNING = ['LD', 'RD', 'LW', 'C', 'RW'];
const KEDJE_ORDNING = { '1st Line': 1, '2nd Line': 2, '3rd Line': 3, '4th Line': 4, '5th Line': 5 };

export function tolkaUppstallning(t) {
  t = t.replace(/\u00a0/g, ' ');
  const domare = t.match(/<strong>Referee\(s\)<\/strong>.*?<td[^>]*>(.*?)<\/td>/s);
  const linje = t.match(/<strong>Linesmen<\/strong>.*?<td[^>]*>(.*?)<\/td>/s);
  const lista = m => m ? rensa(m[1]).split(',').map(x => x.trim()).filter(Boolean) : [];
  const lagen = [];
  for (const d of t.split(/<th class="tdSubTitle" colspan="\d+"><h3>/).slice(1)) {
    const namn = rensa(d.slice(0, d.indexOf('</h3>')));
    const m = namn.match(/^(.*?)\s*\(([^)]*)\)\s*$/);
    const coach = re => { const x = d.match(re); return x ? rensa(x[1]) : ''; };
    const lag = { lag: m ? m[1] : namn, farg: m ? m[2] : '',
      tranare: coach(/Head Coach:\s*<\/strong>(.*?)<\/td>/s), asstranare: coach(/Assistant Coach:\s*<\/strong>(.*?)<\/td>/s),
      malvakter: [], kedjor: [] };
    const rader = alla(/<tr[^>]*>(.*?)<\/tr>/gs, d).map(x => x[1]);
    let i = 0;
    while (i < rader.length) {
      const rub = rader[i].match(/rowspan="2"[^>]*>\s*<strong>(.*?)<\/strong>/s);
      if (!rub) { i++; continue; }
      const rubrik = rensa(rub[1]);
      const block = [rader[i], rader[i + 1] || ''];
      i += 2;
      if (rubrik === 'Goalies') {
        block.forEach(r => alla(/class="lineUpPlayer[^"]*">(.*?)<\/div>/gs, r).forEach(x => {
          const s = spelare(x[1]); if (s) lag.malvakter.push(s);
        }));
        continue;
      }
      const sp = [];
      for (const r of block) {
        const platser = alla(/text-align:\s*(?:right|center|left);?\s*"?\s*(?:\/>|>(.*?)<\/td>)/gs, r).map(x => x[1] || '');
        const namnPos = { 3: ['LW', 'C', 'RW'], 2: ['LD', 'RD'] }[platser.length];
        if (!namnPos) continue;
        namnPos.forEach((pos, j) => {
          const s = spelare(platser[j].replace(/<[^>]+>/g, ''));
          if (s) sp.push({ ...s, pos });
        });
      }
      if (sp.length) lag.kedjor.push({ namn: rubrik, spelare: sp });
    }
    lag.kedjor.sort((a, b) => (KEDJE_ORDNING[a.namn] || 9) - (KEDJE_ORDNING[b.namn] || 9));
    lag.kedjor.forEach(k => k.spelare.sort((a, b) => POS_ORDNING.indexOf(a.pos) - POS_ORDNING.indexOf(b.pos)));
    lagen.push(lag);
  }
  return { domare: lista(domare), linjemän: lista(linje), lag: lagen };
}

export function tolkaHelMatch(eventsHtml, lineupHtml, id = null, serie = null) {
  const m = tolkaHandelser(eventsHtml, id);
  const u = lineupHtml ? tolkaUppstallning(lineupHtml) : { domare: [], linjemän: [], lag: [] };
  m.serie = serie ? String(serie) : null;
  m.domare = u.domare; m.linjemän = u.linjemän;
  const upp = { h: null, b: null };
  for (const lag of u.lag) {
    if (lag.lag === m.hemma && !upp.h) upp.h = lag;
    else if (lag.lag === m.borta && !upp.b) upp.b = lag;
  }
  if (!upp.h && !upp.b && u.lag.length === 2) [upp.h, upp.b] = u.lag;

  // Lagens förkortningar -> h/b: via spelare i laguppställningen, annars via målen
  const nyck = p => `${p.nr}|${p.namn}`;
  const nrNamn = {};
  for (const s of ['h', 'b']) {
    nrNamn[s] = new Set([...((upp[s] || {}).kedjor || []).flatMap(k => k.spelare), ...((upp[s] || {}).malvakter || [])].map(nyck));
  }
  const roster = {};
  for (const e of [...m.handelser, ...m.malvakter]) {
    const p = e.spelare || ('nr' in e ? { nr: e.nr, namn: e.namn } : null);
    if (!p) continue;
    for (const s of ['h', 'b']) {
      if (nrNamn[s].has(nyck(p))) { roster[e.kort] = roster[e.kort] || { h: 0, b: 0 }; roster[e.kort][s]++; }
    }
  }
  const sida = {};
  for (const [k, v] of Object.entries(roster)) sida[k] = v.b > v.h ? 'b' : 'h';
  let forra = [0, 0];
  for (const e of m.handelser) {
    if (e.typ !== 'mal') continue;
    const [x, y] = e.stallning.split('-').map(Number);
    if (!(e.kort in sida)) sida[e.kort] = x > forra[0] ? 'h' : 'b';
    forra = [x, y];
  }
  const kanda = Object.keys(sida);
  if (kanda.length === 1) {
    for (const e of m.handelser) if (e.kort !== kanda[0] && !(e.kort in sida)) sida[e.kort] = sida[kanda[0]] === 'h' ? 'b' : 'h';
  }
  for (const e of m.handelser) { e.lag = sida[e.kort] ?? null; delete e.kort; }
  for (const s of ['h', 'b']) {
    const lag = m.lag[s];
    lag.kort = Object.keys(sida).find(k => sida[k] === s) || '';
    lag.malvakter = m.malvakter.filter(g => sida[g.kort] === s).map(({ kort, ...g }) => g);
    if (upp[s]) Object.assign(lag, { farg: upp[s].farg, tranare: upp[s].tranare, asstranare: upp[s].asstranare,
      uppstallning: { malvakter: upp[s].malvakter, kedjor: upp[s].kedjor } });
    else lag.uppstallning = null;
  }
  delete m.malvakter;
  return m;
}

// Seriens liveöversikt (/StatPage/Live/<serie>/): dagens matcher, med match-id redan före nedsläpp
// (för matcher som rapporteras live - andra står med utan länk). Varje match är ett eget block.
// [{id, hemma, borta, text, perioder, status, klar}] - text är tiden före match, sedan ställningen.
export function tolkaLivevy(html) {
  const ut = [];
  const delar = html.split('<div class="row d-flex d-sm-none">');
  let avsnitt = '';
  delar.forEach((d, i) => {
    if (i > 0) {
      const lag = [...d.matchAll(/<div class="h2 font-weight-bold">(.*?)<\/div>/gs)].map(m => rensa(m[1]));
      const id = (d.match(/\/Game\/Events\/(\d+)/) || [])[1] || null;
      const res = d.match(/class="col-2\s+p-1 text-center Result">([\s\S]*?)<div class="col-5/);
      const rader = res ? [...res[1].matchAll(/<div class="col-12 p-0 m-0 text-center">([\s\S]*?)<\/div>/g)].map(m => rensa(m[1])) : [];
      const status = rensa((d.match(/TodaysGamesGame"><div class="col-12 m-0 text-center">([\s\S]*?)<\/div>/) || [])[1]);
      if (lag.length >= 2) {
        const per = rader.find(r => /^\(.*\)$/.test(r));
        ut.push({ id, hemma: lag[0], borta: lag[1], text: rader[0] || '', perioder: per ? per.slice(1, -1).trim() : '',
          status, klar: /final score/i.test(avsnitt) || /^final score/i.test(status) });
      }
    }
    // Rubriken (Upcoming / In Progress, Final Score) gäller blocken efter den
    const rub = [...d.matchAll(/pageSubTitle">([^<]*)</g)];
    if (rub.length) avsnitt = rub[rub.length - 1][1].trim();
  });
  return ut;
}
