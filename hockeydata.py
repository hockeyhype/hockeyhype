"""Läser och skriver sidans data: en JSON-fil per säsong och distrikt, plus en innehållsförteckning.

    data/index.json                    {"senaste": "2026-27", "sasonger": {"2026-27": {"uppdaterad", "distrikt": [...]}}}
    data/<säsong>/<distrikt>.json      {"distrikt": "Stockholm", "grupper": [...]}

Varje grupp: {"id", "serie", "kategori", "distrikt", "uppdaterad", "endast_tabell",
              "spelare", "tabell", "malvakter", "matcher"} - se README för kolumnerna.
"""
import datetime, json, os, re, unicodedata

MAPP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KATEGORIER = {"U14P": "Pojkar 14 år", "U14F": "Flickor 14 år", "U15P": "Pojkar 15 år",
              "U16P": "Pojkar 16 år", "U16F": "Flickor 16 år", "U18H": "Herrjuniorer 18 år"}


def filnamn(distrikt):
    s = distrikt.lower().replace("å", "a").replace("ä", "a").replace("ö", "o")
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") + ".json"


def las_index(mapp=MAPP):
    fil = os.path.join(mapp, "index.json")
    return json.load(open(fil, encoding="utf8")) if os.path.exists(fil) else {"senaste": None, "sasonger": {}}


def las_sasong(sasong, mapp=MAPP):
    """(uppdaterad, [grupper]) för en säsong, i distriktsordning."""
    info = las_index(mapp)["sasonger"].get(sasong)
    if not info:
        return None, []
    grupper = []
    for d in info["distrikt"]:
        grupper += json.load(open(os.path.join(mapp, sasong, d["fil"]), encoding="utf8"))["grupper"]
    return info["uppdaterad"], grupper


def skriv_livekandidater(sasong, grupper, mapp=MAPP):
    """data/live-kandidater.json: dagens och de två närmaste dagarnas matcher, för Cloudflare-workern
    som bevakar pågående matcher (se worker/). Kort fil - workern läser den varannan minut."""
    idag = datetime.date.today()
    dagar = {(idag + datetime.timedelta(days=i)).isoformat() for i in range(3)}
    matcher = []
    for g in grupper:
        for m in g["matcher"]["kommande"]:
            if m[0][:10] in dagar:
                matcher.append({"serie": g["id"], "tid": m[0], "hemma": m[1], "borta": m[2]})
    with open(os.path.join(mapp, "live-kandidater.json"), "w", encoding="utf8", newline="\n") as f:
        json.dump({"sasong": sasong, "skapad": datetime.datetime.now().isoformat(timespec="minutes"),
                   "matcher": sorted(matcher, key=lambda m: m["tid"])}, f, ensure_ascii=False, separators=(",", ":"))


def spara_sasong(sasong, uppdaterad, grupper, mapp=MAPP):
    """Skriver en fil per distrikt (i den ordning distrikten först förekommer) och uppdaterar index.json."""
    ordning = []
    for g in grupper:
        if g["distrikt"] not in ordning:
            ordning.append(g["distrikt"])
    os.makedirs(os.path.join(mapp, sasong), exist_ok=True)
    distrikt = []
    for d in ordning:
        gs = [g for g in grupper if g["distrikt"] == d]
        fil = filnamn(d)
        with open(os.path.join(mapp, sasong, fil), "w", encoding="utf8", newline="\n") as f:
            json.dump({"distrikt": d, "grupper": gs}, f, ensure_ascii=False, separators=(",", ":"))
        distrikt.append({"namn": d, "fil": fil, "grupper": len(gs)})
    skriv_livekandidater(sasong, grupper, mapp)
    index = las_index(mapp)
    # tid = klockslaget for korningen (svensk tid - GitHub-korningen har TZ=Europe/Stockholm)
    index["sasonger"][sasong] = {"uppdaterad": uppdaterad, "tid": datetime.datetime.now().strftime("%H:%M"),
                                 "distrikt": distrikt}
    index["senaste"] = max(index["sasonger"])
    with open(os.path.join(mapp, "index.json"), "w", encoding="utf8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
