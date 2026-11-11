"""Hämtar serietabell, spelar-/målvaktsstatistik och matcher för en serie från stats.swehockey.se.

Datat returneras i samma format som Hockeykoll använder (se README.md).
Sidorna cachas per dag i cache/ÅÅÅÅ-MM-DD så att en omkörning samma dag inte hämtar allt igen.
"""
import datetime, html, os, re, time, urllib.request

BASE = "https://stats.swehockey.se"
TODAY = datetime.date.today().isoformat()
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", TODAY)


def get(path):
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, path.strip("/").replace("/", "_") + ".html")
    if os.path.exists(fn):
        return open(fn, encoding="utf8").read()
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        try:
            t = urllib.request.urlopen(req, timeout=60).read().decode("utf8", "replace")
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
    open(fn, "w", encoding="utf8").write(t)
    time.sleep(0.3)  # snällt mot swehockey
    return t


def clean(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def rows(fragment):
    return [[clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", fragment, flags=re.S)]


def content(t):
    i = t.find('id="groupStandingResultContent"')
    if i < 0:
        i = t.find('class="tblContent"')
    return t[i:]


def num(x):
    try:
        return int(x)
    except ValueError:
        try:
            f = float(x.replace(",", "."))
            return int(f) if f == int(f) else f
        except ValueError:
            return 0


def standings(gid):
    """[placering, lag, GP, W, T, L, målskillnad, poäng] - bara totaltabellen."""
    res = []
    for c in rows(content(get(f"/ScheduleAndResults/Standings/{gid}"))):
        if len(c) >= 9 and c[1] and re.fullmatch(r"-?\d+", c[2]) and re.search(r"\d+:\d+", c[6]):
            res.append([num(c[0]) if c[0] else None, c[1], num(c[2]), num(c[3]), num(c[4]), num(c[5]), num(c[7]), num(c[8])])
    # Sidan har även hemma/borta/senaste 5-tabeller - sluta när lagen börjar upprepas
    seen, tot = set(), []
    for r in res:
        if r[1] in seen:
            break
        seen.add(r[1])
        tot.append(r)
    for i, r in enumerate(tot):
        if r[0] is None:  # delad placering visas som tom cell
            r[0] = tot[i - 1][0]
    return tot


def last_update(t):
    m = re.search(r"Last update:\s*(\d{4}-\d{2}-\d{2})", html.unescape(t).replace("\xa0", " "))
    return m.group(1) if m else None


def roster_births(gid):
    """{(lag, namn): födelseår} från lagens trupplistor."""
    births, team = {}, None
    for c in rows(content(get(f"/Teams/Info/TeamRoster/{gid}"))):
        if len(c) >= 2 and c[-1] == "[Top]":
            team = c[-2]
        elif len(c) >= 4 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c[2]):
            births[(team, c[1])] = c[2][:4]
    return births


def players_by_team(gid):
    """Utespelare: [namn, lag, pos, födelseår, GP, G, A, TP, PIM]
    Målvakter:  [namn, lag, födelseår, GPT, GKD, GPI, MIP, GA, SVS, SOG, SVS%, GAA, SO, W, L]"""
    players, goalies = [], []
    team = mode = None
    for c in rows(content(get(f"/Teams/Info/PlayersByTeam/{gid}"))):
        if c and c[-1] == "[Top]":
            team = c[-2]
        elif c[:4] == ["Rk", "No", "Name", "Pos"]:
            mode = "p"
        elif c[:4] == ["Rk", "No", "Name", "GPT"]:
            mode = "g"
        elif mode == "p" and len(c) >= 9 and c[2] and re.fullmatch(r"\d+", c[4]):
            players.append([c[2], team, c[3], None] + [num(x) for x in c[4:9]])
        elif mode == "g" and len(c) >= 15 and c[2] and re.fullmatch(r"\d+", c[3]):
            goalies.append([c[2], team, None, num(c[3]), num(c[4]), num(c[5]), c[6]] + [num(x) for x in c[7:15]])
    return players, goalies


def schedule(gid):
    """spelade: [datum, hemma, borta, hemmamål, bortamål, arena] (senaste först)
    kommande: ["datum tid", hemma, borta, arena] (närmast först)"""
    spelade, kommande, date = [], [], None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", content(get(f"/ScheduleAndResults/Schedule/{gid}")), flags=re.S):
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        if not cells:
            continue
        # Vissa serier har en Round-kolumn först, och datum står ibland bara på dagens första match
        di = next((i for i, c in enumerate(cells[:3]) if re.match(r"\d{4}-\d{2}-\d{2}", c)), None)
        if di is not None:
            date = cells[di][:10]
            tm0 = re.search(r"\d{4}-\d{2}-\d{2}\s+(\d{1,2}:\d{2})", cells[di])
            cells = ([tm0.group(1)] if tm0 else []) + cells[di + 1:]
        game_idx = next((i for i, c in enumerate(cells) if " - " in c and not re.fullmatch(r"[\d\s\-]+", c)), None)
        if game_idx is None or date is None:
            continue
        tm = re.search(r"(\d{1,2}:\d{2})", " ".join(cells[:game_idx]))
        home, away = [s.strip() for s in cells[game_idx].split(" - ", 1)]
        rest = cells[game_idx + 1:]
        venue = rest[-1] if len(rest) >= 2 else ""
        rm = re.fullmatch(r"(\d+)\s*-\s*(\d+)", rest[0] if rest else "")
        if rm:
            spelade.append([date, home, away, int(rm.group(1)), int(rm.group(2)), venue])
        else:
            kommande.append([f"{date} {tm.group(1) if tm else ''}".strip(), home, away, venue])
    spelade.sort(key=lambda r: r[0], reverse=True)
    kommande.sort(key=lambda r: r[0])
    return {"spelade": spelade, "kommande": kommande}


def group(gid, serie, kategori, endast_tabell=False):
    if endast_tabell:
        # U14: bara serietabellen (en sida per serie)
        return {"id": gid, "serie": serie, "kategori": kategori, "uppdaterad": TODAY, "endast_tabell": True,
                "spelare": [], "tabell": standings(gid), "malvakter": [], "matcher": {"spelade": [], "kommande": []}}
    births = roster_births(gid)
    sp, gk = players_by_team(gid)
    for r in sp:
        r[3] = births.get((r[1], r[0]))
    for r in gk:
        r[2] = births.get((r[1], r[0]))
    return {"id": gid, "serie": serie, "kategori": kategori, "uppdaterad": TODAY, "endast_tabell": False,
            "spelare": sp, "tabell": standings(gid), "malvakter": gk, "matcher": schedule(gid)}
