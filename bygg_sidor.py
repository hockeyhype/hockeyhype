"""Bygger statiska, sökmotorvänliga sidor ur datan i index.html.

    python bygg_sidor.py --ut _site

Skriver (i --ut):
  serier/index.html            alla serier och lag för senaste säsongen
  serie/<id>/index.html        tabell, kommande matcher och senaste resultat för en serie
  lag/<slug>/index.html        ett lags placering, matcher och resultat i alla dess serier
  sitemap.xml, robots.txt

Sidorna innehåller bara tabeller och matcher - inga spelarnamn, så att barns namn inte blir egna
sökträffar. Den interaktiva sidan (index.html) länkas från varje sida.
"""
import argparse, datetime, html, os, re, unicodedata
import uppdatera

BAS = "https://hockeyhype.se"
KATEGORIER = {"U15P": "Pojkar 15 år", "U16P": "Pojkar 16 år", "U18H": "Herrjuniorer 18 år"}
MANADER = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "aug", "sep", "okt", "nov", "dec"]
e = html.escape


def las_sasong(sida):
    """Senaste säsongen i index.html: (säsong, uppdaterad, [grupper])."""
    rader = open(sida, encoding="utf8").read().split("\n")
    sasonger = [(m.group(1), i) for i, l in enumerate(rader) if (m := re.match(r'^"(\d{4}-\d{2})": \{$', l.strip()))]
    sasong, start = max(sasonger)
    uppdaterad, grupper = None, []
    for l in rader[start + 1:]:
        if l.strip().startswith("]"):
            break
        if l.strip().startswith("uppdaterad:"):
            uppdaterad = re.search(r'"([^"]*)"', l).group(1)
        if uppdatera.GROUP_RE.match(l):
            grupper.append(uppdatera.parse_group(l))
    return sasong, uppdaterad, grupper


def slug(namn):
    s = unicodedata.normalize("NFKD", namn.lower().replace("å", "a").replace("ä", "a").replace("ö", "o"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def datum(d):
    # "2026-11-04" eller "2026-11-04 19:30" -> "4 nov" / "4 nov 19:30"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{1,2}:\d{2}))?", d or "")
    if not m:
        return e(d or "")
    s = f"{int(m.group(3))} {MANADER[int(m.group(2)) - 1]}"
    return s + (f" {m.group(4)}" if m.group(4) and m.group(4) != "00:00" else "")


def riktigt_lag(namn):
    # Kvalserier har platshållare som "PL. 5 U16P Blå Grupp 1" innan lagen är klara
    return bool(namn) and not namn.startswith("PL.")


CSS = """
:root{--bg:#F1F2F6;--surface:#FFFFFF;--border:#D0D4E2;--text:#141B2E;--text-muted:#555F7A;--text-faint:#848EAA;
  --accent:#8E2430;--accent-strong:#6E1B25;--banner-bg:#182640;--banner-ink:#FFFFFF;--thead-bg:#FAEDEF;--thead-ink:#182640;
  --u15:#293B63;--u16:#8E2430;--u18:#8A6D1F;--pos:#293B63;color-scheme:light;}
@media (prefers-color-scheme: dark){:root{--bg:#0C1220;--surface:#141C30;--border:#2E3A5E70;--text:#EBEEF6;--text-muted:#9AA3C0;
  --text-faint:#69739A;--accent:#E0576A;--accent-strong:#EC7C8B;--banner-bg:#3B1620;--banner-ink:#F6C9CF;--thead-bg:transparent;
  --thead-ink:#69739A;--u15:#3A4C78;--u16:#A8394A;--u18:#8A6D1F;--pos:#9DB0E8;color-scheme:dark;}}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--text);font-family:"Karla",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased;}
.wrap{max-width:880px;margin:0 auto;padding:20px 16px 56px;}
header{display:flex;align-items:baseline;justify-content:space-between;gap:12px;flex-wrap:wrap;padding-bottom:14px;margin-bottom:18px;border-bottom:2px solid var(--accent);}
.wordmark{font-family:"Oswald",sans-serif;font-weight:700;font-size:28px;line-height:1;color:var(--text);text-decoration:none;}
.wordmark .hype{color:var(--accent);} .wordmark .se{color:var(--text-faint);font-weight:500;font-size:.6em;}
header nav a{font-size:14px;font-weight:600;color:var(--text-muted);text-decoration:none;margin-left:14px;}
header nav a:hover{color:var(--accent);}
.brod{font-size:13px;color:var(--text-faint);margin-bottom:6px;} .brod a{color:var(--text-muted);}
h1,h2{font-family:"Oswald",sans-serif;font-weight:600;letter-spacing:.01em;margin:0;line-height:1.2;}
h1{font-size:30px;margin-bottom:6px;} h2{font-size:19px;margin:0 0 10px;}
.lead{color:var(--text-muted);margin:0 0 16px;}
.knapp{display:inline-block;background:var(--accent);color:#fff;font-weight:700;font-size:14px;padding:9px 16px;border-radius:8px;text-decoration:none;}
.knapp:hover{background:var(--accent-strong);}
.kort{background:var(--surface);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-top:18px;}
.kort > h2{background:var(--banner-bg);color:var(--banner-ink);border-left:3px solid var(--accent);font-family:"Karla",sans-serif;font-size:15px;font-weight:700;padding:10px 14px;margin:0;}
.kort > h2 a{color:inherit;}
.kort .inre{padding:12px 14px;}
table{width:100%;border-collapse:collapse;font-size:14px;}
th{background:var(--thead-bg);color:var(--thead-ink);font-size:11px;text-transform:uppercase;letter-spacing:.04em;text-align:right;padding:7px 6px;}
td{padding:7px 6px;border-top:1px solid var(--border);text-align:right;font-variant-numeric:tabular-nums;}
th:first-child,td:first-child{text-align:left;width:28px;color:var(--text-faint);}
th:nth-child(2),td:nth-child(2){text-align:left;}
td:nth-child(2){font-weight:600;} td a{color:var(--text);text-decoration:none;} td a:hover{color:var(--accent);text-decoration:underline;}
td.p{font-weight:700;color:var(--accent-strong);}
tr.markerad td{background:var(--thead-bg);}
.matcher{list-style:none;margin:0;padding:0;}
.matcher li{display:flex;gap:12px;align-items:baseline;padding:8px 14px;border-top:1px solid var(--border);font-size:14px;}
.matcher li:first-child{border-top:0;}
.matcher .d{flex:none;width:92px;color:var(--text-muted);font-size:13px;}
.matcher .m{flex:1;min-width:0;} .matcher .r{flex:none;font-family:"Oswald",sans-serif;font-weight:700;color:var(--accent-strong);}
.matcher .a{flex:none;color:var(--text-faint);font-size:12px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.tom{color:var(--text-faint);font-style:italic;padding:10px 14px;margin:0;}
.chip{font-family:"Oswald",sans-serif;font-size:12px;font-weight:600;padding:1px 7px;border-radius:5px;color:#fff;margin-right:6px;}
.c-U15P{background:var(--u15);} .c-U16P{background:var(--u16);} .c-U18H{background:var(--u18);}
.lista{columns:2 220px;column-gap:24px;margin:0;padding:12px 14px;list-style:none;}
.lista li{padding:3px 0;break-inside:avoid;} .lista a{color:var(--text);} .lista a:hover{color:var(--accent);}
.lista .n{color:var(--text-faint);font-size:13px;}
.rad{margin:4px 0 0;color:var(--text-muted);font-size:14px;}
footer{margin-top:28px;font-size:13px;color:var(--text-faint);} footer a{color:var(--text-muted);}
@media (max-width:560px){.matcher li{flex-wrap:wrap;gap:2px 10px;} .matcher .d{width:auto;} .matcher .a{display:none;} h1{font-size:25px;}}
"""


def sida(titel, beskrivning, sokvag, innehall, sasong):
    url = BAS + sokvag
    return f"""<!doctype html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beskrivning)}">
<link rel="canonical" href="{url}">
<meta property="og:title" content="{e(titel)}">
<meta property="og:description" content="{e(beskrivning)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{BAS}/og.png">
<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:locale" content="sv_SE">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="stylesheet" href="/fonts/fonts.css">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <a class="wordmark" href="/" aria-label="hockeyhype.se - till startsidan">hockey<span class="hype">hype</span><span class="se">.se</span></a>
  <nav><a href="/">Tabeller och statistik</a><a href="/serier/">Alla serier och lag</a></nav>
</header>
<main>
{innehall}
</main>
<footer>Säsong {sasong.replace("-", "/")}. Data hämtad från Svenska Ishockeyförbundets statistiksida <a href="https://stats.swehockey.se">stats.swehockey.se</a>.
Frågor eller fel? <a href="mailto:kontakt@hockeyhype.se">kontakt@hockeyhype.se</a> · <a href="/om.html">Om sidan och integritet</a></footer>
</div>
</body>
</html>
"""


def match_li(m, spelad):
    if spelad:
        d, hemma, borta, hm, bm, arena = m
        return (f'<li><span class="d">{datum(d)}</span><span class="m">{e(hemma)} – {e(borta)}</span>'
                f'<span class="r">{hm}–{bm}</span><span class="a">{e(arena or "")}</span></li>')
    d, hemma, borta, arena = m
    return (f'<li><span class="d">{datum(d)}</span><span class="m">{e(hemma)} – {e(borta)}</span>'
            f'<span class="a">{e(arena or "")}</span></li>')


def matchlista(matcher, spelade, tomt):
    if not matcher:
        return f'<p class="tom">{tomt}</p>'
    return '<ul class="matcher">' + "".join(match_li(m, spelade) for m in matcher) + "</ul>"


def tabell(g, lagslug, markera=None):
    if not g["tabell"]:
        return '<p class="tom">Ingen tabell publicerad ännu.</p>'
    rader = []
    for plac, lag, gp, w, t, l, gd, p in g["tabell"]:
        namn = f'<a href="/lag/{lagslug[lag]}/">{e(lag)}</a>' if lag in lagslug else e(lag)
        cls = ' class="markerad"' if lag == markera else ""
        rader.append(f"<tr{cls}><td>{plac}</td><td>{namn}</td><td>{gp}</td><td>{w}</td><td>{t}</td><td>{l}</td>"
                     f'<td>{"+" if gd > 0 else ""}{gd}</td><td class="p">{p}</td></tr>')
    return ('<table><thead><tr><th>#</th><th>Lag</th><th title="Spelade">GP</th><th title="Vinster">W</th>'
            '<th title="Oavgjorda">T</th><th title="Förluster">L</th><th title="Målskillnad">+/-</th><th title="Poäng">P</th></tr></thead>'
            "<tbody>" + "".join(rader) + "</tbody></table>")


def lag_i_grupp(g):
    namn = {r[1] for r in g["tabell"]}
    for m in g["matcher"]["spelade"] + g["matcher"]["kommande"]:
        namn.update(m[1:3])
    return {n for n in namn if riktigt_lag(n)}


def skriv(ut, relativ, text):
    fil = os.path.join(ut, relativ)
    os.makedirs(os.path.dirname(fil), exist_ok=True)
    open(fil, "w", encoding="utf8", newline="\n").write(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sida", default="index.html")
    ap.add_argument("--ut", required=True)
    args = ap.parse_args()

    sasong, uppdaterad, grupper = las_sasong(args.sida)
    sas = sasong.replace("-", "/")
    uppd = datum(uppdaterad) + (f" {uppdaterad[:4]}" if uppdaterad else "")
    ordning = list(KATEGORIER)
    grupper.sort(key=lambda g: (ordning.index(g["kategori"]) if g["kategori"] in ordning else 99, g["serie"]))

    # Lag -> unik slug, och vilka serier varje lag spelar i
    lagens_grupper = {}
    for g in grupper:
        for lag in lag_i_grupp(g):
            lagens_grupper.setdefault(lag, []).append(g)
    lagslug, upptagna = {}, set()
    for lag in sorted(lagens_grupper):
        s = slug(lag) or "lag"
        while s in upptagna:
            s += "-2"
        upptagna.add(s)
        lagslug[lag] = s

    adresser = [("/", "daily"), ("/serier/", "daily"), ("/om.html", "monthly")]

    # En sida per serie
    for g in grupper:
        kat = KATEGORIER.get(g["kategori"], g["kategori"])
        sokvag = f"/serie/{g['id']}/"
        kommande = g["matcher"]["kommande"][:12]
        spelade = g["matcher"]["spelade"][:12]
        ledare = g["tabell"][0] if g["tabell"] else None
        beskr = f"Tabell, resultat och kommande matcher för {g['serie']} ({kat}), säsong {sas}."
        if ledare:
            beskr += f" {ledare[1]} leder med {ledare[7]} poäng."
        innehall = f"""<div class="brod"><a href="/serier/">Alla serier</a> › {e(kat)}</div>
<h1>{e(g['serie'])}</h1>
<p class="lead"><span class="chip c-{e(g['kategori'])}">{e(g['kategori'])}</span>Tabell, resultat och kommande matcher, säsong {sas}. Uppdaterad {uppd}.</p>
<a class="knapp" href="/#serie/{g['id']}">Öppna serien med poängliga och statistik →</a>
<section class="kort"><h2>Tabell</h2>{tabell(g, lagslug)}</section>
<section class="kort"><h2>Kommande matcher</h2>{matchlista(kommande, False, "Inga kommande matcher inlagda.")}</section>
<section class="kort"><h2>Senaste resultat</h2>{matchlista(spelade, True, "Inga spelade matcher ännu.")}</section>
<p class="rad">Källa: <a href="https://stats.swehockey.se/ScheduleAndResults/Overview/{g['id']}">{e(g['serie'])} på stats.swehockey.se</a></p>"""
        skriv(args.ut, f"serie/{g['id']}/index.html",
              sida(f"{g['serie']} – tabell och resultat {sas} | Hockeyhype", beskr, sokvag, innehall, sasong))
        adresser.append((sokvag, "daily"))

    # En sida per lag (alla serier laget spelar i)
    for lag, lg in lagens_grupper.items():
        sokvag = f"/lag/{lagslug[lag]}/"
        delar = []
        for g in lg:
            kat = KATEGORIER.get(g["kategori"], g["kategori"])
            rad = next((r for r in g["tabell"] if r[1] == lag), None)
            plac = (f"Plats {rad[0]} av {len(g['tabell'])} · {rad[7]} poäng på {rad[2]} matcher"
                    if rad else "Ingen tabellplacering ännu")
            kommande = [m for m in g["matcher"]["kommande"] if lag in m[1:3]][:5]
            spelade = [m for m in g["matcher"]["spelade"] if lag in m[1:3]][:5]
            delar.append(f"""<section class="kort"><h2><a href="/serie/{g['id']}/">{e(g['serie'])}</a></h2>
<div class="inre"><span class="chip c-{e(g['kategori'])}">{e(g['kategori'])}</span>{e(kat)} · <strong>{plac}</strong>
<p class="rad"><a href="/#lag/{g['id']}/{e(_url(lag))}">Lagets poängliga och statistik →</a></p></div>
{tabell(g, lagslug, markera=lag)}
<div class="inre"><h2>Nästa matcher</h2></div>{matchlista(kommande, False, "Inga kommande matcher inlagda.")}
<div class="inre"><h2>Senaste resultat</h2></div>{matchlista(spelade, True, "Inga spelade matcher ännu.")}
</section>""")
        serienamn = ", ".join(g["serie"] for g in lg)
        beskr = f"{lag}: tabellplacering, resultat och kommande matcher säsong {sas} i {serienamn}."
        innehall = f"""<div class="brod"><a href="/serier/">Alla serier och lag</a> › {e(lag)}</div>
<h1>{e(lag)}</h1>
<p class="lead">Tabellplacering, resultat och kommande matcher i {len(lg)} {"serie" if len(lg) == 1 else "serier"}, säsong {sas}. Uppdaterad {uppd}.</p>
{"".join(delar)}"""
        skriv(args.ut, f"lag/{lagslug[lag]}/index.html",
              sida(f"{lag} – tabell, resultat och matcher {sas} | Hockeyhype", beskr, sokvag, innehall, sasong))
        adresser.append((sokvag, "daily"))

    # Översikt: alla serier och lag
    sektioner = []
    for kod, kat in KATEGORIER.items():
        gs = [g for g in grupper if g["kategori"] == kod]
        if gs:
            sektioner.append(f'<section class="kort"><h2>{e(kat)} ({kod})</h2><ul class="lista">' + "".join(
                f'<li><a href="/serie/{g["id"]}/">{e(g["serie"])}</a> <span class="n">{len(g["tabell"]) or len(lag_i_grupp(g))} lag</span></li>'
                for g in gs) + "</ul></section>")
    lagrad = "".join(f'<li><a href="/lag/{lagslug[l]}/">{e(l)}</a></li>' for l in sorted(lagslug, key=str.lower))
    innehall = f"""<h1>Alla serier och lag</h1>
<p class="lead">Stockholms ungdomshockey säsong {sas}: {len(grupper)} serier och {len(lagslug)} lag. Uppdaterad {uppd}.</p>
<a class="knapp" href="/">Till tabeller och spelarstatistik →</a>
{"".join(sektioner)}
<section class="kort"><h2>Lag A–Ö</h2><ul class="lista">{lagrad}</ul></section>"""
    skriv(args.ut, "serier/index.html",
          sida(f"Alla serier och lag – ungdomshockey Stockholm {sas} | Hockeyhype",
               f"Tabeller, resultat och kommande matcher för alla {len(grupper)} serier och {len(lagslug)} lag i Stockholms ungdomshockey (U15, U16 och U18) säsong {sas}.",
               "/serier/", innehall, sasong))

    idag = datetime.date.today().isoformat()
    skriv(args.ut, "sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
              f"  <url><loc>{BAS}{a}</loc><lastmod>{idag}</lastmod><changefreq>{f}</changefreq></url>\n" for a, f in adresser)
          + "</urlset>\n")
    skriv(args.ut, "robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BAS}/sitemap.xml\n")
    print(f"Byggde {len(grupper)} seriesidor, {len(lagslug)} lagsidor, översikt och sitemap ({len(adresser)} adresser)")


def _url(s):
    from urllib.parse import quote
    return quote(s, safe="")


if __name__ == "__main__":
    main()
