"""Den dagliga uppdateringen av hockeyhype.se (körs av GitHub Actions).

    python dagligen.py                  # hämtar bara det som kan ha ändrats (se nedan)
    python dagligen.py --full           # hämtar allt (veckokörningen och körningar för hand)
    python dagligen.py --bevaka --las-om 22390,21450   # samma, plus dessa serier (väckning från workern)
    python dagligen.py --bevaka         # matchbevakningen (var 10:e minut): bara serier med en match
                                        # som nyss borde ha tagit slut, och sparar bara om något ändrats

1. Läser vilka serier som ska med från serier.json (skapas av hitta_serier.py).
2. Hämtar serierna från swehockey, men bara det som behövs:
   - Avslutade serier (inga kommande matcher kvar) hämtas inte alls.
   - Övriga serier: spelschemat hämtas (en sida). Har det kommit nya eller ändrade resultat sedan
     förra körningen - eller hände det i går eller i dag - hämtas även tabell och spelarstatistik.
     Annars behålls dem och bara schemat uppdateras (t.ex. flyttade matcher).
   - Trupplistan (födelseår) hämtas bara när det finns spelare vi inte känner igen.
   - U14-serier (endast_tabell) har ingen spelarstatistik: bara tabell och spelschema.
   Med --full hämtas allt för alla serier. Det fångar rättelser, borttagna spelare och ändringar
   som schemat inte avslöjar.
3. Kontrollerar varje serie mot förra körningen. Ser en serie trasig ut - den kraschar, tabellen
   blir tom, färre matcher eller lag, eller betydligt färre spelare - behålls förra körningens data
   för just den serien och det skrivs ut som en varning. Resten uppdateras som vanligt.
4. Skriver data/<säsong>/<distrikt>.json och data/index.json, och en sammanfattning.
   Om mer än en fjärdedel av serierna får behålla gammal data avbryts körningen (exit 1) utan att
   något sparas - då har swehockey troligen ändrat något, och GitHub mejlar om felet.
"""
import argparse, datetime, json, os, sys, traceback

MAPP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, MAPP)
import hockeydata, matchdata, swehockey

IGAR = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
# Matchbevakningen: en match bevakas från FORST efter nedsläpp tills resultatet finns (högst SIST)
BEVAKA_FORST = datetime.timedelta(minutes=75)
BEVAKA_SIST = datetime.timedelta(hours=6)


def match_att_bevaka(old, nu):
    """Första kommande match i serien som borde vara slutspelad men saknar resultat (eller None)."""
    if not old:
        return None
    for m in old["matcher"]["kommande"]:
        try:
            start = datetime.datetime.strptime(m[0], "%Y-%m-%d %H:%M")
        except ValueError:
            continue  # tid saknas
        if start + BEVAKA_FORST <= nu <= start + BEVAKA_SIST:
            return m
    return None


def utan_id(spelade):
    """Spelade matcher utan match-id:t (sjunde kolumnen) - id:t är ingen ändring i sig."""
    return [r[:6] for r in spelade]


def har_id(g):
    return all(len(r) >= 7 for r in g["matcher"]["spelade"])


def utan_tidsstampel(g):
    return {k: v for k, v in g.items() if k != "uppdaterad"}


def hamta(s, old, full, bevaka=False):
    """Hämtar en serie. Returnerar (grupp, sätt) där sätt är full, schema, avslutad eller tabell."""
    gid = s["id"]
    if s.get("endast_tabell"):
        # U14: tabell och spelschema. Samma regler som nedan: avslutade serier hämtas inte, och
        # tabellen hämtas bara när schemat visar nya resultat (eller hände i går eller i dag).
        if old and not full and old["matcher"]["spelade"] and not old["matcher"]["kommande"] and har_id(old):
            return old, "avslutad"
        matcher = swehockey.schedule(gid)
        andrad = swehockey.TODAY if not old or utan_id(matcher["spelade"]) != utan_id(old["matcher"]["spelade"]) else old.get("andrad")
        if old and not full and andrad == old.get("andrad") and (bevaka or (andrad or "") < IGAR):
            return dict(old, matcher=matcher, uppdaterad=swehockey.TODAY), "schema"
        return {"id": gid, "serie": s["serie"], "kategori": s["kategori"], "uppdaterad": swehockey.TODAY,
                "endast_tabell": True, "andrad": andrad, "spelare": [], "tabell": swehockey.standings(gid),
                "malvakter": [], "matcher": matcher}, "tabell"

    # Utan tidigare data, eller med --full, hämtas allt
    if old and not full:
        # (avslutade serier från före match-id:na läses om en gång för att få id:na)
        if old["matcher"]["spelade"] and not old["matcher"]["kommande"] and har_id(old):
            return old, "avslutad"
        matcher = swehockey.schedule(gid)
        nytt = utan_id(matcher["spelade"]) != utan_id(old["matcher"]["spelade"])
        # Statistiken kan fyllas i efter att resultatet förts in - hämta därför fullt ett dygn till
        # (inte i matchbevakningen, som annars skulle hämta allt var 10:e minut - kvällskörningen tar det)
        nyligen = not bevaka and (old.get("andrad") or "") >= IGAR
        if not nytt and not nyligen:
            return dict(old, matcher=matcher, uppdaterad=swehockey.TODAY), "schema"
    else:
        matcher = swehockey.schedule(gid)

    sp, gk = swehockey.players_by_team(gid)
    kanda = {}
    if old:
        kanda = {(r[1], r[0]): r[3] for r in old["spelare"] if r[3]}
        kanda.update({(r[1], r[0]): r[2] for r in old["malvakter"] if r[2]})
    okanda = any((r[1], r[0]) not in kanda for r in sp + gk)
    # Trupplistan hämtas vid --full, när det finns spelare vi inte känner igen, och när
    # spelarstatistiken är tom (t.ex. DM före första matchen - truppen kan ändå vara publicerad)
    trupp = swehockey.roster(gid) if full or okanda or not sp else None
    fodda = {(lag, namn): ar for lag, namn, ar, _ in trupp} if trupp is not None else kanda
    for r in sp:
        r[3] = fodda.get((r[1], r[0]))
    for r in gk:
        r[2] = fodda.get((r[1], r[0]))
    # Spelare i truppen som inte spelat ännu (finns inte i statistiken) läggs till med 0 i allt,
    # så att lagsidan visar hela truppen. Hämtades inte truppen nu behålls förra körningens rader.
    i_statistik = {(r[1], r[0]) for r in sp + gk}
    if trupp is not None:
        sp += [[namn, lag, pos, ar, 0, 0, 0, 0, 0, None] for lag, namn, ar, pos in trupp if (lag, namn) not in i_statistik]
    elif old:
        sp += [r for r in old["spelare"] if r[4] == 0 and (r[1], r[0]) not in i_statistik]
    andrad = swehockey.TODAY if not old or utan_id(matcher["spelade"]) != utan_id(old["matcher"]["spelade"]) else old.get("andrad")
    return {"id": gid, "serie": s["serie"], "kategori": s["kategori"], "uppdaterad": swehockey.TODAY,
            "endast_tabell": False, "andrad": andrad, "spelare": sp, "tabell": swehockey.standings(gid),
            "malvakter": gk, "matcher": matcher}, "full"


def hamta_matcher(sasong, grupper, data, max_antal):
    """Hämtar matchsidorna (data/<säsong>/matcher/<id>.json) för spelade matcher som saknar fil eller
    inte är fastställda än. Nyaste först, högst max_antal per körning (första gången finns hela
    säsongen att hämta - det sprids då över några körningar). Ej fastställda matcher äldre än två
    veckor hämtas inte om. Fel stoppar inte körningen."""
    grans = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    att_hamta = []
    for g in grupper:
        for r in g["matcher"]["spelade"]:
            mid = r[6] if len(r) >= 7 else None
            if not mid:
                continue
            fil = os.path.join(matchdata.mapp(sasong, data), f"{mid}.json")
            if not os.path.exists(fil) or (r[0] >= grans and matchdata.behover(sasong, mid, data)):
                att_hamta.append((r[0], mid, g["id"]))
    att_hamta.sort(reverse=True)
    hamtade, fel = 0, []
    for _, mid, serie in att_hamta[:max_antal]:
        try:
            matchdata.hamta_och_spara(sasong, mid, serie, data)
            hamtade += 1
        except Exception as e:
            fel.append(f"match {mid} (serie {serie}): {e}")
    kvar = max(0, len(att_hamta) - max_antal)
    print(f"Matchsidor: {hamtade} hämtade" + (f", {kvar} kvar till nästa körning" if kvar else "")
          + (f", {len(fel)} fel" if fel else ""))
    for f in fel[:10]:
        print("  " + f)
    return hamtade


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
    ap.add_argument("--full", action="store_true", help="hämta allt för alla serier")
    ap.add_argument("--bevaka", action="store_true", help="bara serier med en nyss avslutad match utan resultat")
    ap.add_argument("--las-om", default="", help="med --bevaka: läs dessutom om dessa serier (kommaseparerade id), "
                    "t.ex. när Cloudflare-workern sett att en match är slut")
    ap.add_argument("--matcher", type=int, default=None,
                    help="högst så många matchsidor per körning (standard 400, 40 i matchbevakningen)")
    args = ap.parse_args()

    konfig = json.load(open(args.serier, encoding="utf8"))
    sasong = konfig["sasong"]
    _, gamla = hockeydata.las_sasong(sasong, args.data)
    gamla = {g["id"]: g for g in gamla}

    grupper, par, varningar, antal, satt = [], [], [], 0, {}
    nu = datetime.datetime.now()
    tvingade = {x.strip() for x in args.las_om.split(",") if x.strip()}  # svensk tid (TZ=Europe/Stockholm i GitHub-körningen)
    print("Hämtar allt (--full)" if args.full else "Matchbevakning" if args.bevaka else "Hämtar bara det som kan ha ändrats")
    for distrikt, info in konfig["distrikt"].items():
        for s in info["grupper"]:
            antal += 1
            old = gamla.get(s["id"])
            if args.bevaka:
                m = match_att_bevaka(old, nu)
                if not m and s["id"] in tvingade and old:
                    m = ["(väckt av workern)", s["serie"], "", ""]
                if not m:
                    if old:
                        old["distrikt"] = distrikt
                        grupper.append(old)
                    continue
                print(f"bevakar  {s['serie']}: {m[1]} - {m[2]} ({m[0]})", flush=True)
            try:
                new, hur = hamta(s, old, args.full, args.bevaka)
                satt[hur] = satt.get(hur, 0) + 1
                print(f"{hur:9} {distrikt}: {s['serie']} ({s['id']})", flush=True)
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

    # Matchsidorna: i matchbevakningen bara för serierna som lästes om nu
    max_matcher = args.matcher if args.matcher is not None else (40 if args.bevaka else 400)
    nya_matcher = hamta_matcher(sasong, [n for o, n in par if n is not o] if args.bevaka else grupper,
                                args.data, max_matcher)

    if args.bevaka and all(new is old or utan_tidsstampel(new) == utan_tidsstampel(old) for old, new in par):
        if nya_matcher:
            print(f"KLART: {nya_matcher} matchsidor sparade, inga serier ändrade")
            return 0
        print(f"KLART: inget nytt ({len(par)} serier kontrollerade, {swehockey.ANROP['natverk']} sidor från swehockey) - sparar inget")
        return 0
    hockeydata.spara_sasong(sasong, swehockey.TODAY, grupper, args.data)
    sammanstallning = ", ".join(f"{n} {h}" for h, n in sorted(satt.items()))
    print(f"KLART: {len(grupper)} serier sparade i {args.data} ({sammanstallning}). "
          f"Sidor från swehockey: {swehockey.ANROP['sidor']} ({swehockey.ANROP['natverk']} över nätet, resten från cache)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
