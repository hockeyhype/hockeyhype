"""Matchsidor: händelser, statistik och laguppställning för en match från stats.swehockey.se.

    data/<säsong>/matcher/<match-id>.json

En fil per spelad match (id:t är swehockeys, från länken i spelschemat). Hämtas av dagligen.py när
matchen dyker upp som spelad, och igen tills sekretariatet fastställt resultatet ("Final Score").
Sidan (index.html) läser filen när någon öppnar matchen. Formatet:

    {"id", "serie", "datum", "tid", "arena", "publik", "hemma", "borta", "h", "b",
     "perioder": [[h, b], ...], "status", "klar", "senast",
     "lag": {"h": LAG, "b": LAG}, "domare": [...], "linjemän": [...], "handelser": [HÄNDELSE, ...]}

    LAG = {"kort", "farg", "tranare", "asstranare", "skott": [per period], "raddningar": [per period],
           "pim", "pp", "pptid", "malvakter": [{"nr", "namn", "rdd", "skott"}],
           "uppstallning": {"malvakter": [SPELARE], "kedjor": [{"namn", "spelare": [SPELARE + "pos"]}]}}
    SPELARE = {"nr", "namn"}; pos = LD, RD, LW, C, RW
    HÄNDELSE = {"period", "tid", "typ": mal|utv|mv_in|mv_ut|timeout, "lag": h|b, ...}
        mal: "stallning", "lage" (EQ, PP1, SH1, GWS ...), "spelare", "malnr", "assist": [SPELARE]
        utv: "spelare" (eller saknas för lagstraff), "min", "orsak"
        mv_in/mv_ut: "spelare"
Händelserna ligger i matchordning (swehockey visar senaste först).

Samma tolkning finns i worker/src/matchdata.js (matcher som inte är klara, via /api/match/<id>) -
ändra båda. Jämför med python verktyg/test_matchdata.py och node worker/test/test.mjs.
"""
import html, json, os, re

import swehockey

# Höjs när tolkningen ändras - då hämtas redan sparade matcher om (dagligen.py, hamta_matcher)
VERSION = 2


def _text(s):
    return swehockey.clean(s or "")


def _spelare(s):
    """"29. Blid, Wilmer" -> {"nr": 29, "namn": "Blid, Wilmer"}."""
    m = re.match(r"\s*(\d+)\.\s*(.+?)\s*$", _text(s))
    return {"nr": int(m.group(1)), "namn": m.group(2)} if m else None


def _tal(s):
    return [int(x) for x in re.findall(r"\d+", s or "")]


def tolka_handelser(t, id=None):
    """Events-sidan -> dict (utan laguppställning). Lagens förkortningar (NSK, SSK) kopplas till
    hemma/borta i tolka_match, med hjälp av laguppställningen."""
    t = t.replace("\xa0", " ")
    h2 = re.search(r"<h2>([^<]+?)\s-\s([^<]+)</h2>", t)
    hemma, borta = (html.unescape(h2.group(1)).strip(), html.unescape(h2.group(2)).strip()) if h2 else ("", "")
    h3 = [_text(x) for x in re.findall(r"<h3[^>]*>(.*?)</h3>", t[:t.find("Actions</h2>")] if "Actions</h2>" in t else t, flags=re.S)]
    datum = tid = ""
    arena = ""
    if h3:
        m = re.match(r"(\d{4}-\d{2}-\d{2})\s*(\d{1,2}:\d{2})?", h3[0])
        if m:
            datum, tid = m.group(1), m.group(2) or ""
        if len(h3) >= 3:
            arena = h3[2]

    info = re.search(r'class="tdInfoArea"[^>]*>(.*?)</td>', t, flags=re.S)
    divar = [_text(d) for d in re.findall(r"<div[^>]*>(.*?)</div>", info.group(1), flags=re.S)] if info else []
    stalln = next((d for d in divar if re.fullmatch(r"\d+\s*-\s*\d+", d)), None)
    h, b = (_tal(stalln) + [None, None])[:2] if stalln else (None, None)
    perioder = [[int(x), int(y)] for x, y in re.findall(r"(\d+)-(\d+)", next((d for d in divar if re.fullmatch(r"\(.*\)", d)), ""))]
    publik = next((_tal(d)[0] for d in divar if re.match(r"(spectators|åskådare|publik)", d, re.I) and _tal(d)), None)
    status = next((d for d in divar if d != stalln and not re.fullmatch(r"\(.*\)", d)
                   and not re.match(r"(spectators|åskådare|publik)", d, re.I)), "")

    # Statistikraderna: <td>Shots</td><td><strong>23</strong></td><td>(11:12)</td> ... samma för bortalaget
    lag = {"h": {}, "b": {}}
    for namn, nyckel in (("Shots", "skott"), ("Saves", "raddningar"), ("PIM", "pim"), ("PP", "pp")):
        trff = re.findall(r'<td class="tdOdd ?">\s*' + namn + r'\s*</td>\s*<td class="tdOdd ?">\s*<strong>(.*?)</strong>\s*</td>\s*'
                          r'<td class="tdOdd leftPad">(.*?)</td>', t, flags=re.S)
        for sida, (varde, inom) in zip(("h", "b"), trff):
            varde, inom = _text(varde), _text(inom)
            if nyckel in ("skott", "raddningar"):
                lag[sida][nyckel] = [int(x) for x in re.findall(r"\d+", inom)]
            elif nyckel == "pim":
                lag[sida]["pim"] = _tal(varde)[0] if _tal(varde) else 0
            else:
                lag[sida]["pp"] = varde
                lag[sida]["pptid"] = inom.strip("() ")

    senast = re.search(r"Last update:\s*([\d-]+ [\d:]+)", t)
    res = {"v": VERSION, "id": str(id) if id else None, "datum": datum, "tid": tid, "arena": arena, "publik": publik,
           "hemma": hemma, "borta": borta, "h": h, "b": b, "perioder": perioder, "status": status,
           "klar": status.lower() == "final score", "senast": senast.group(1) if senast else None, "lag": lag}

    # Händelserna: rubriker per period och rader med tid, typ, lag, spelare, ev. orsak
    del_ = t[t.find("Actions</h2>"):] if "Actions</h2>" in t else ""
    malvakter, handelser, period = [], [], ""
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", del_, flags=re.S):
        rubrik = re.search(r"<h3>(.*?)</h3>", tr, flags=re.S)
        if rubrik:
            period = _text(rubrik.group(1))
            continue
        celler = re.findall(r"<td[^>]*?(?:/>|>(.*?)</td>)", tr, flags=re.S)
        if period == "Goalkeeper Summary":
            c = [x for x in celler if _text(x)]
            if len(c) >= 3:
                sp = _spelare(c[1])
                rs = re.search(r"\((\d+)/(\d+)\)", _text(c[2]))
                if sp:
                    malvakter.append({"kort": _text(c[0]), **sp,
                                      "rdd": int(rs.group(1)) if rs else None, "skott": int(rs.group(2)) if rs else None})
            continue
        if len(celler) < 4 or not re.fullmatch(r"\d{1,3}:\d{2}", _text(celler[0])):
            continue
        tid_, typ, kort, rest = _text(celler[0]), _text(celler[1]), _text(celler[2]), celler[3] or ""
        # swehockey lägger orsaken (utvisningar) som en <td> inuti spelarens <td> - dela där
        rest, _, inbaddad = rest.partition("<td")
        orsak_cell = re.sub(r"^[^>]*>", "", inbaddad) if inbaddad else (celler[4] if len(celler) > 4 else "")
        e = {"period": period, "tid": tid_, "kort": kort}
        mal = re.fullmatch(r"(\d+-\d+)\s*\(([^)]*)\)", typ)
        if mal:
            # Målskytten står först; efter den kommer målantalet (<span>, saknas ibland) och assisten (<div>)
            huvud = re.split(r"<span|<div", rest, maxsplit=1)[0]
            assist = [_spelare(a) for a in re.findall(r"<div[^>]*>(.*?)</div>", rest, flags=re.S)]
            malnr = re.search(r'title="[^"]*goals[^"]*"\s*>\s*\((\d+)\)', rest, flags=re.S)
            e.update(typ="mal", stallning=mal.group(1), lage=mal.group(2), spelare=_spelare(huvud),
                     malnr=int(malnr.group(1)) if malnr else None, assist=[a for a in assist if a])
        elif re.fullmatch(r"\d+ min", typ):
            orsak = re.split(r"<br\s*/?>", orsak_cell)[0]
            e.update(typ="utv", min=int(typ.split()[0]), spelare=_spelare(rest), orsak=_text(orsak))
        elif typ in ("GK In", "GK Out"):
            e.update(typ="mv_in" if typ == "GK In" else "mv_ut", spelare=_spelare(rest))
        elif typ == "TO":
            e.update(typ="timeout")
        else:
            e.update(typ="annat", text=" ".join(x for x in (typ, _text(rest), _text(orsak_cell)) if x))
        handelser.append(e)
    # swehockey visar senaste perioden och händelsen först - vänd till matchordning
    res["handelser"] = handelser[::-1]
    res["malvakter"] = malvakter
    return res


def tolka_uppstallning(t):
    """LineUps-sidan -> {"domare", "linjemän", "lag": [LAG, LAG]} (hemma först)."""
    t = t.replace("\xa0", " ")
    domare = re.search(r"<strong>Referee\(s\)</strong>.*?<td[^>]*>(.*?)</td>", t, flags=re.S)
    linje = re.search(r"<strong>Linesmen</strong>.*?<td[^>]*>(.*?)</td>", t, flags=re.S)
    lista = lambda m: [x.strip() for x in _text(m.group(1)).split(",") if x.strip()] if m else []
    alla = []
    delar = re.split(r'<th class="tdSubTitle" colspan="\d+"><h3>', t)[1:]
    for d in delar:
        namn = _text(d[:d.find("</h3>")])
        m = re.match(r"(.*?)\s*\(([^)]*)\)\s*$", namn)
        lag = {"lag": m.group(1) if m else namn, "farg": m.group(2) if m else "",
               "tranare": "", "asstranare": "", "malvakter": [], "kedjor": []}
        tr_ = _text(re.search(r"Head Coach:\s*</strong>(.*?)</td>", d, flags=re.S).group(1)) if "Head Coach:" in d else ""
        ass = _text(re.search(r"Assistant Coach:\s*</strong>(.*?)</td>", d, flags=re.S).group(1)) if "Assistant Coach:" in d else ""
        lag["tranare"], lag["asstranare"] = tr_, ass
        # Varje block: rubrik (Goalies / 1st Line ...) med rowspan=2 och två rader spelare
        rader = re.findall(r"<tr[^>]*>(.*?)</tr>", d, flags=re.S)
        i = 0
        while i < len(rader):
            rub = re.search(r'rowspan="2"[^>]*>\s*<strong>(.*?)</strong>', rader[i])
            if not rub:
                i += 1
                continue
            rubrik = _text(rub.group(1))
            block = [rader[i], rader[i + 1] if i + 1 < len(rader) else ""]
            i += 2
            if rubrik == "Goalies":
                for r in block:
                    lag["malvakter"] += [s for s in (_spelare(x) for x in re.findall(r'class="lineUpPlayer[^"]*">(.*?)</div>', r, flags=re.S)) if s]
                continue
            spelare = []
            for r in block:
                # Platserna i swehockeys ordning (vänster kolumn först), tomma platser räknas med:
                # anfallsraden har tre (LW, C, RW), backraden två (LD, RD)
                platser = re.findall(r'text-align:\s*(?:right|center|left);?\s*"?\s*(?:/>|>(.*?)</td>)', r, flags=re.S)
                namn_pos = {3: ["LW", "C", "RW"], 2: ["LD", "RD"]}.get(len(platser))
                if not namn_pos:
                    continue
                for pos, inneh in zip(namn_pos, platser):
                    sp = _spelare(re.sub(r"<[^>]+>", "", inneh or ""))
                    if sp:
                        sp["pos"] = pos
                        spelare.append(sp)
            if spelare:
                lag["kedjor"].append({"namn": rubrik, "spelare": spelare})
        alla.append(lag)
    ordning = {"1st Line": 1, "2nd Line": 2, "3rd Line": 3, "4th Line": 4, "5th Line": 5}
    for lag in alla:
        lag["kedjor"].sort(key=lambda k: ordning.get(k["namn"], 9))
        for k in lag["kedjor"]:
            k["spelare"].sort(key=lambda s: ["LD", "RD", "LW", "C", "RW"].index(s["pos"]))
    return {"domare": lista(domare), "linjemän": lista(linje), "lag": alla}


def tolka_match(events_html, lineup_html, id=None, serie=None):
    m = tolka_handelser(events_html, id)
    u = tolka_uppstallning(lineup_html) if lineup_html else {"domare": [], "linjemän": [], "lag": []}
    m["serie"] = str(serie) if serie else None
    m["domare"], m["linjemän"] = u["domare"], u["linjemän"]
    upp = {"h": None, "b": None}
    for lag in u["lag"]:
        if lag["lag"] == m["hemma"] and not upp["h"]:
            upp["h"] = lag
        elif lag["lag"] == m["borta"] and not upp["b"]:
            upp["b"] = lag
    if not upp["h"] and not upp["b"] and len(u["lag"]) == 2:
        upp["h"], upp["b"] = u["lag"]

    # Lagens förkortningar -> h/b: via spelare i laguppställningen, annars via målen (vem ställningen ökade för)
    nr_namn = {s: {(p["nr"], p["namn"]) for k in (upp[s] or {}).get("kedjor", []) for p in k["spelare"]}
                  | {(p["nr"], p["namn"]) for p in (upp[s] or {}).get("malvakter", [])} for s in ("h", "b")}
    roster = {}
    for e in m["handelser"] + m["malvakter"]:
        p = e.get("spelare") or ({"nr": e["nr"], "namn": e["namn"]} if "nr" in e else None)
        if p:
            for s in ("h", "b"):
                if (p["nr"], p["namn"]) in nr_namn[s]:
                    roster.setdefault(e["kort"], {"h": 0, "b": 0})[s] += 1
    sida = {k: max(v, key=v.get) for k, v in roster.items()}
    forra = (0, 0)
    for e in m["handelser"]:
        if e["typ"] == "mal":
            x, y = map(int, e["stallning"].split("-"))
            sida.setdefault(e["kort"], "h" if x > forra[0] else "b")
            forra = (x, y)
    if len(set(sida.values())) == 1 and len(sida) == 1:
        # Bara ett lag känt - det andra är den andra förkortningen
        kanda = next(iter(sida))
        for e in m["handelser"]:
            if e["kort"] != kanda:
                sida.setdefault(e["kort"], "b" if sida[kanda] == "h" else "h")
    for e in m["handelser"]:
        e["lag"] = sida.get(e.pop("kort"))
    for s in ("h", "b"):
        kort = next((k for k, v in sida.items() if v == s), "")
        lag = m["lag"][s]
        lag["kort"] = kort
        lag["malvakter"] = [{k: v for k, v in g.items() if k != "kort"} for g in m["malvakter"] if sida.get(g["kort"]) == s]
        if upp[s]:
            lag.update(farg=upp[s]["farg"], tranare=upp[s]["tranare"], asstranare=upp[s]["asstranare"],
                       uppstallning={"malvakter": upp[s]["malvakter"], "kedjor": upp[s]["kedjor"]})
        else:
            lag["uppstallning"] = None
    del m["malvakter"]
    return m


# ---------- hämtning (dagligen.py) ----------

def mapp(sasong, data=None):
    return os.path.join(data or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"), sasong, "matcher")


def las(sasong, mid, data=None):
    """Den sparade matchen, eller None."""
    fil = os.path.join(mapp(sasong, data), f"{mid}.json")
    try:
        return json.load(open(fil, encoding="utf8"))
    except (OSError, ValueError):
        return None


def behover(sasong, mid, data=None):
    """Ska matchen (om)hämtas? Ja om filen saknas eller resultatet inte är fastställt."""
    m = las(sasong, mid, data)
    return not m or not m.get("klar")


def hamta_och_spara(sasong, mid, serie, data=None):
    ev = swehockey.get(f"/Game/Events/{mid}", cache=False)
    lu = swehockey.get(f"/Game/LineUps/{mid}", cache=False)
    m = tolka_match(ev, lu, mid, serie)
    if not m["hemma"]:
        raise ValueError(f"match {mid}: ingen matchsida")
    os.makedirs(mapp(sasong, data), exist_ok=True)
    with open(os.path.join(mapp(sasong, data), f"{mid}.json"), "w", encoding="utf8", newline="\n") as f:
        json.dump(m, f, ensure_ascii=False, separators=(",", ":"))
    return m
