"""Hela den dagliga Hockeykoll-körningen i ett kommando (används av den schemalagda uppgiften).

    python C:/Users/linus/Documents/SweHockeyScraper/dagligen.py --live <fil från Artifact read> --ut <katalog>
    python dagligen.py --sida index.html          # GitHub: uppdaterar index.html på plats

1. Om den publicerade sidan (--live) har ändrats av någon annan utgår körningen från den.
2. Hämtar säsongens serier från swehockey och kontrollerar att inget ser trasigt ut.
3. Sparar sidan (--sida, standard hockeykoll.html här i mappen) och, med --ut, en kopia i <katalog>/hockeykoll.html.
4. Skriver ut en sammanfattning och sist en rad "PUBLICERA: <fil>" eller "AVBRUTET: <orsak>".
"""
import argparse, os, shutil, sys, traceback

MAPP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MAPP)
import swehockey, uppdatera

LOKAL = os.path.join(MAPP, "hockeykoll.html")


def winpath(p):
    # Git Bash-sökvägar (/c/Users/...) -> C:\Users\..., och \\?\-prefix för sökvägar över 260 tecken
    if p.startswith("/") and len(p) > 2 and p[2] == "/":
        p = p[1].upper() + ":" + p[2:]
    p = os.path.abspath(p)
    return "\\\\?\\" + p if os.name == "nt" and not p.startswith("\\\\?\\") else p


def innehall(t):
    # Publiceringen lägger ett eget skal runt sidan - jämför bara från <title> och framåt
    i = t.find("<title>")
    return t[i:].strip() if i >= 0 else t.strip()


def sammanfatta(par):
    rader = []
    for old, new in par:
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


def kontrollera(par, varningar):
    fel = list(varningar)
    for old, new in par:
        if len(new["matcher"]["spelade"]) < len(old["matcher"]["spelade"]):
            fel.append(f"{new['serie']}: färre spelade matcher än förut "
                       f"({len(old['matcher']['spelade'])} -> {len(new['matcher']['spelade'])})")
        if len(new["spelare"]) < 0.8 * len(old["spelare"]):
            fel.append(f"{new['serie']}: betydligt färre spelare än förut "
                       f"({len(old['spelare'])} -> {len(new['spelare'])})")
        if len(new["tabell"]) < len(old["tabell"]):
            fel.append(f"{new['serie']}: färre lag i tabellen än förut")
    return fel


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", help="den publicerade sidan, sparad av Artifact read")
    ap.add_argument("--ut", help="katalog att skriva en kopia av sidan till, för publicering som artefakt")
    ap.add_argument("--sida", default=LOKAL, help="sidan som uppdateras på plats")
    ap.add_argument("--sasong", default="2026-27")
    args = ap.parse_args()

    sida = os.path.abspath(args.sida)
    lokal = open(sida, encoding="utf8").read()
    bas = lokal
    if args.live:
        live = open(winpath(args.live), encoding="utf8").read()
        if innehall(live) != innehall(lokal):
            print("Den publicerade sidan skiljer sig från den lokala kopian - utgår från den publicerade.")
            shutil.copyfile(sida, os.path.join(os.path.dirname(sida), "hockeykoll.forra.html"))
            bas = live
        else:
            print("Den publicerade sidan är densamma som den lokala kopian.")

    lines = bas.split("\n")
    try:
        par, varningar = uppdatera.uppdatera_sasong(lines, args.sasong)
    except Exception:
        traceback.print_exc()
        print("AVBRUTET: skriptet kraschade (se felet ovan) - swehockey kan ha ändrat sina sidor")
        return 1

    fel = kontrollera(par, varningar)
    print()
    rader = sammanfatta(par)
    print("SAMMANFATTNING")
    print("\n".join(rader) if rader else "Inga nya resultat eller ändrade matchtider.")
    print()
    if fel:
        print("Publicerar inte, något ser fel ut:")
        print("\n".join("  " + f for f in fel))
        print("AVBRUTET: " + "; ".join(fel))
        return 1

    resultat = "\n".join(lines)
    open(sida, "w", encoding="utf8").write(resultat)
    ut = sida
    if args.ut:
        os.makedirs(winpath(args.ut), exist_ok=True)
        ut = os.path.join(winpath(args.ut), "hockeykoll.html")
        open(ut, "w", encoding="utf8").write(resultat)
    print("PUBLICERA: " + ut.replace("\\\\?\\", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
