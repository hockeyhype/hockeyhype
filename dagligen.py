"""Den dagliga uppdateringen av hockeyhype.se (körs av GitHub Actions).

    python dagligen.py                  # uppdaterar säsongen i serier.json, skriver data/
    python dagligen.py --serier serier.json --data data

1. Läser vilka serier som ska med från serier.json (skapas av hitta_serier.py).
2. Hämtar varje serie från swehockey. U14-serier (endast_tabell) hämtar bara tabellen.
3. Kontrollerar varje serie mot förra körningen. Ser en serie trasig ut - den kraschar, tabellen
   blir tom, färre matcher eller lag, eller betydligt färre spelare - behålls förra körningens data
   för just den serien och det skrivs ut som en varning. Resten uppdateras som vanligt.
4. Skriver data/<säsong>/<distrikt>.json och data/index.json, och en sammanfattning.
   Om mer än en fjärdedel av serierna får behålla gammal data avbryts körningen (exit 1) utan att
   något sparas - då har swehockey troligen ändrat något, och GitHub mejlar om felet.
"""
import argparse, json, os, sys, traceback

MAPP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MAPP)
import hockeydata, swehockey


def sammanfatta(par):
    rader = []
    for old, new in par:
        if not old or new is old:
            continue
        gamla = {tuple(m[:3]) for m in old["matcher"]["spelade"]}
        nya = [m for m in new["matcher"]["spelade"] if tuple(m[:3]) not in gamla]
        gamla_k = {(m[1], m[2]): m for m in old["matcher"]["kommande"]}
        flyttade = []
        for m in new["matcher"]["kommande"]:
            o = gamla_k.get((m[1], m[2]))
            if o and (o[0] != m[0] or o[3] != m[3]):
                flyttade.append((o, m))
        if not nya and not flyttade:
            continue
        ledare = new["tabell"][0] if new["tabell"] else None
        rubrik = f"{new['serie']}"
        if ledare:
            rubrik += f" (leder: {ledare[1]}, {ledare[7]} p på {ledare[2]} matcher)"
        rader.append(rubrik)
        for m in sorted(nya, key=lambda m: m[0]):
            rader.append(f"  resultat {m[0]}: {m[1]} - {m[2]} {m[3]}-{m[4]}")
        for o, m in flyttade:
            plats = f" ({m[3]})" if o[3] != m[3] else ""
            rader.append(f"  ny tid: {m[1]} - {m[2]}, {o[0]} -> {m[0]}{plats}")
    return rader


def fel_i_serie(old, new):
    """Skäl att inte lita på en nyhämtad serie, jämfört med förra körningen (eller None)."""
    if not old:
        return None
    if not new["tabell"] and old.get("tabell"):
        return "tom tabell"
    if len(new["tabell"]) < len(old["tabell"]):
        return f"färre lag i tabellen ({len(old['tabell'])} -> {len(new['tabell'])})"
    if len(new["matcher"]["spelade"]) < len(old["matcher"]["spelade"]):
        return f"färre spelade matcher ({len(old['matcher']['spelade'])} -> {len(new['matcher']['spelade'])})"
    if len(new["spelare"]) < 0.8 * len(old["spelare"]):
        return f"betydligt färre spelare ({len(old['spelare'])} -> {len(new['spelare'])})"
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--serier", default=os.path.join(MAPP, "serier.json"))
    ap.add_argument("--data", default=hockeydata.MAPP)
    args = ap.parse_args()

    konfig = json.load(open(args.serier, encoding="utf8"))
    sasong = konfig["sasong"]
    _, gamla = hockeydata.las_sasong(sasong, args.data)
    gamla = {g["id"]: g for g in gamla}

    grupper, par, varningar, antal = [], [], [], 0
    for distrikt, info in konfig["distrikt"].items():
        for s in info["grupper"]:
            antal += 1
            old = gamla.get(s["id"])
            print(f"Hämtar {distrikt}: {s['serie']} ({s['id']})...", flush=True)
            try:
                new = swehockey.group(s["id"], s["serie"], s["kategori"], s.get("endast_tabell", False))
                skal = fel_i_serie(old, new)
            except Exception:
                traceback.print_exc()
                new, skal = None, "kraschade vid hämtningen"
            if skal:
                varningar.append(f"{s['serie']} ({s['id']}): {skal}" + (" - behåller förra körningens data" if old else " - hoppar över"))
                if not old:
                    continue
                new = old
            new["distrikt"] = distrikt
            grupper.append(new)
            par.append((old, new))

    print()
    rader = sammanfatta(par)
    print("SAMMANFATTNING")
    print("\n".join(rader) if rader else "Inga nya resultat eller ändrade matchtider.")
    if varningar:
        print("\nVARNINGAR")
        print("\n".join("  " + v for v in varningar))
    print()
    if len(varningar) > antal / 4:
        print(f"AVBRUTET: {len(varningar)} av {antal} serier gick inte att uppdatera - swehockey kan ha ändrat sina sidor")
        return 1

    hockeydata.spara_sasong(sasong, swehockey.TODAY, grupper, args.data)
    print(f"KLART: {len(grupper)} serier sparade i {args.data}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
