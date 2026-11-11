"""Läser och skriver sidans data: en JSON-fil per säsong och distrikt, plus en innehållsförteckning.

    data/index.json                    {"senaste": "2026-27", "sasonger": {"2026-27": {"uppdaterad", "distrikt": [...]}}}
    data/<säsong>/<distrikt>.json      {"distrikt": "Stockholm", "grupper": [...]}

Varje grupp: {"id", "serie", "kategori", "distrikt", "uppdaterad", "endast_tabell",
              "spelare", "tabell", "malvakter", "matcher"} - se README för kolumnerna.
"""
import json, os, re, unicodedata

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
    index = las_index(mapp)
    index["sasonger"][sasong] = {"uppdaterad": uppdaterad, "distrikt": distrikt}
    index["senaste"] = max(index["sasonger"])
    with open(os.path.join(mapp, "index.json"), "w", encoding="utf8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
