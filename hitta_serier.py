"""Hittar alla ungdomsserier (grupper) för en säsong i valda distrikt på stats.swehockey.se.

    python hitta_serier.py                    # region Öst, skriver serier.json
    python hitta_serier.py --distrikt Stockholm Uppland

Går igenom distriktets meny på swehockey, plockar ut ungdomsligorna (U14-U16 pojkar och flickor)
och listar säsongens grupper i varje liga. Cuper, träningsmatcher och yngre åldrar hoppas över.
Resultatet sparas i serier.json och läses av uppdateringen.
"""
import argparse, html, json, os, re
import hockeydata, swehockey

# Distriktens startsidor på swehockey (en liga i distriktet - menyn är densamma på alla dess sidor)
DISTRIKT = {
    "Stockholm": {"region": "Öst", "id": "22117"},
    "Uppland": {"region": "Öst", "id": "22022"},
    "Södermanland": {"region": "Öst", "id": "22017"},
    "Gotland": {"region": "Öst", "id": "11256"},  # inga egna ungdomsserier 2026-27 - lagen spelar i Stockholm
}
# Serier som ligger under regionen och inte under något distrikt, men som hör till region Öst
REGIONSERIER = {"Öst": ["21274", "21271", "22243", "22242", "21267", "21742", "21741"]}

SASONG = "2026-27"
NAVORD = {"Schedule & Results", "Live", "Overview", "Schedule", "Standings", "Tot/H/A"}
SKIPPA = re.compile(r"cup|trophy|games|träning|preseas|camp|turnering|poolspel|vårcup|elitcup|kom in", re.I)


def kategori(namn):
    """'U15P Blå Grupp 1' -> U15P, 'U16 P Södermanland' -> U16P, 'F14 ...' -> U14F, 'U14' -> U14P."""
    n = namn.replace("\xa0", " ")
    m = re.match(r"\s*U\s?(\d{2})\s?([PF])\b", n) or re.match(r"\s*U\s?(\d{2})\b()", n)
    if m:
        return f"U{m.group(1)}{m.group(2) or 'P'}"
    m = re.match(r"\s*F\s?(\d{2})\b", n)
    if m:
        return f"U{m.group(1)}F"
    m = re.match(r"\s*U\s?(\d{2})\s?H\b", n)
    return f"U{m.group(1)}H" if m else None


def text(s):
    return re.sub(r"\s+", " ", html.unescape(s).replace("\xa0", " ")).strip()


def lankar(t):
    return [(typ, gid, text(namn)) for typ, gid, namn in
            re.findall(r'<a href="/ScheduleAndResults/(\w+)/(\d+)"[^>]*>\s*([^<]*?)\s*</a>', t)]


def distriktsmeny(did):
    """Distriktets ligor: rullgardinslistan på distriktets sidor (säsongslistan hoppas över)."""
    t = swehockey.get(f"/ScheduleAndResults/Overview/{did}")
    meny = []
    for gid, namn in re.findall(r'<option[^>]*value="/ScheduleAndResults/\w+/(\d+)"[^>]*>([^<]*)</option>', t):
        namn = text(namn)
        if not re.fullmatch(r"\d{4}-\d{2}", namn) and (gid, namn) not in meny:
            meny.append((gid, namn))
    return meny


def ligans_grupper(gid, foljd=True):
    """Grupperna i ligans trädmeny för säsongen, t.ex. 'U15P Blå Grupp 1', 'U15P DM Röd Grupp 2'."""
    t = swehockey.get(f"/ScheduleAndResults/Overview/{gid}")
    poster = re.findall(r'<li class="(\w+Item) list-group-item[^"]*">\s*(?:<[^a][^>]*>\s*)*'
                        r'<a href="/ScheduleAndResults/(\w+)/(\d+)">\s*([^<]*?)\s*</a>', t)
    grupper, i_sasong = [], False
    for klass, typ, id_, namn in poster:
        namn = text(namn)
        if re.fullmatch(r"\d{4}-\d{2}", namn):
            if i_sasong:
                break
            if namn == SASONG and klass != "openItem":
                # Menyn pekade på en äldre säsong - följ länken till den aktuella
                return ligans_grupper(id_, False) if foljd else []
            i_sasong = namn == SASONG
            continue
        # Mellannivåer i trädet heter bara som kategorin ("U15P") och är inga egna grupper
        if not i_sasong or namn in NAVORD or re.fullmatch(r"(U\s?\d{2}\s?[PFH]?|F\s?\d{2})", namn):
            continue
        if id_ not in [g[0] for g in grupper]:
            grupper.append((id_, namn))
    return grupper


def skriv_ut(namn, grupper, extra=""):
    print(f"{namn}: {extra}{len(grupper)} grupper")
    for g in grupper:
        print(f"   {g['id']}  {g['kategori']:5} {'(tabell) ' if g['endast_tabell'] else ''}{g['serie']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--distrikt", nargs="*", default=list(DISTRIKT))
    ap.add_argument("--ut", default="serier.json")
    args = ap.parse_args()

    resultat = {"sasong": SASONG, "distrikt": {}}
    for d in args.distrikt:
        info = DISTRIKT[d]
        ligor = [(gid, namn) for gid, namn in distriktsmeny(info["id"])
                 if kategori(namn) and not SKIPPA.search(namn) and int(kategori(namn)[1:3]) >= 14]
        grupper = []
        for gid, liganamn in ligor:
            for id_, namn in ligans_grupper(gid):
                kat = kategori(namn) or kategori(liganamn)
                if not kat or SKIPPA.search(namn) or id_ in [g["id"] for g in grupper]:
                    continue
                grupper.append({"id": id_, "serie": namn, "kategori": kat,
                                "endast_tabell": kat.startswith("U14")})
        if grupper:
            resultat["distrikt"][d] = {"region": info["region"], "grupper": grupper}
        skriv_ut(d, grupper, f"{len(ligor)} ligor, ")

    # U18-serierna spelas på regionnivå och ligger inte under något distrikt
    kanda = {g["id"]: g["serie"] for g in hockeydata.las_sasong(SASONG)[1]}
    for region, ids in REGIONSERIER.items():
        grupper = []
        for id_ in ids:
            namn = dict(ligans_grupper(id_)).get(id_) or kanda.get(id_, id_)
            grupper.append({"id": id_, "serie": namn, "kategori": kategori(namn) or "U18H", "endast_tabell": False})
        resultat["distrikt"][f"Region {region}"] = {"region": region, "grupper": grupper}
        skriv_ut(f"Region {region}", grupper)
    open(args.ut, "w", encoding="utf8").write(json.dumps(resultat, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
