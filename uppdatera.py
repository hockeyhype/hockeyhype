"""Uppdaterar en säsong i Hockeykoll-sidan med färsk data från stats.swehockey.se.

Användning:
    python uppdatera.py hockeykoll.html                 # uppdaterar 2026-27
    python uppdatera.py hockeykoll.html --sasong 2027-28

Skriver en ny fil bredvid originalet (hockeykoll.uppdaterad.html) och skriver ut vad som ändrats.
Vilka serier som hämtas styrs av vilka serier (id) som redan finns under säsongen i sidan.
"""
import argparse, json, os, re, sys
import swehockey

GROUP_RE = re.compile(r'^(\s*)\{id:"(\d+)", serie:(".*?"), kategori:(".*?"), uppdaterad:"[^"]*", spelare: ')


def parse_group(line):
    # Raderna är JS-objekt där de första nycklarna saknar citattecken - gör om till JSON
    js = line.strip().rstrip(",")
    js = re.sub(r'^\{id:', '{"id":', js)
    js = re.sub(r', (serie|kategori|uppdaterad|spelare|tabell):', r', "\1":', js)
    js = js.replace(" tabell:", '"tabell":')
    return json.loads(js)


def format_group(indent, g, trailing_comma):
    d = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    return (f'{indent}{{id:"{g["id"]}", serie:{d(g["serie"])}, kategori:{d(g["kategori"])}, '
            f'uppdaterad:"{g["uppdaterad"]}", spelare: {d(g["spelare"])}, tabell:{d(g["tabell"])},'
            f'"malvakter":{d(g["malvakter"])},"matcher":{d(g["matcher"])}}}' + ("," if trailing_comma else ""))


def uppdatera_sasong(lines, sasong):
    """Uppdaterar säsongens serier i sidans rader (in place).
    Returnerar [(gammal, ny), ...] per serie och en lista med varningar."""
    start = next((i for i, l in enumerate(lines) if l.strip() == f'"{sasong}": {{'), None)
    if start is None:
        raise ValueError(f"Hittar inte säsongen {sasong} i sidan")
    par, varningar = [], []
    i = start + 1
    while not lines[i].strip().startswith("]"):
        l = lines[i]
        if l.strip().startswith("uppdaterad:"):
            lines[i] = re.sub(r'"[^"]*"', f'"{swehockey.TODAY}"', l, count=1)
        m = GROUP_RE.match(l)
        if m:
            old = parse_group(l)
            print(f"Hämtar {old['serie']} ({old['id']})...", flush=True)
            # Sidan speglar swehockey: det som tagits bort där (spelare, födelseår) försvinner även här
            new = swehockey.group(old["id"], old["serie"], old["kategori"])
            if not new["tabell"] and old.get("tabell"):
                varningar.append(f"tom tabell för {old['serie']} - sidformatet kan ha ändrats, behåller gammal data")
                par.append((old, old))
            else:
                lines[i] = format_group(m.group(1), new, l.rstrip().endswith(","))
                par.append((old, new))
        i += 1
    return par, varningar


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("--sasong", default="2026-27")
    args = ap.parse_args()

    lines = open(args.html, encoding="utf8").read().split("\n")
    try:
        par, varningar = uppdatera_sasong(lines, args.sasong)
    except ValueError as e:
        sys.exit(str(e))
    changed = []
    for old, new in par:
        diff = [k for k in ("tabell", "spelare", "malvakter", "matcher") if old.get(k) != new[k]]
        if diff:
            n = len(new["matcher"]["spelade"]) - len(old["matcher"]["spelade"])
            changed.append(f"  {old['serie']}: {n:+d} spelade matcher, ändrat: {', '.join(diff)}")
    for v in varningar:
        print("  VARNING: " + v)

    base, ext = os.path.splitext(args.html)
    out = base + ".uppdaterad" + ext
    open(out, "w", encoding="utf8").write("\n".join(lines))
    print("\nÄndringar:" if changed else "\nInga ändringar sedan förra uppdateringen.")
    print("\n".join(changed))
    print(f"\nSkrev {out}")


if __name__ == "__main__":
    main()
