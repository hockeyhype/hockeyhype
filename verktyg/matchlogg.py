"""Loggar kvällens matcher var 3:e minut 17:25-21:45: hockeyhype.se/api/live (workerns läge) och
swehockeys matchsidor (händelser + laguppställning), även före nedsläpp. Används för att se hur
swehockeys matchsidor fylls på under en match. Körs för hand i GitHub Actions (matchlogg.yml),
sparar i mappen matchlogg/ som laddas upp som artefakt."""
import datetime, json, os, re, time, urllib.request

MAPP = os.environ.get("MATCHLOGG", "matchlogg")
os.makedirs(MAPP, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (compatible; hockeyhype-live; +https://hockeyhype.se/om.html)"}
START, SLUT = "17:25", "21:45"


def hamta(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf8", "replace")


def logg(rad):
    with open(os.path.join(MAPP, "logg.txt"), "a", encoding="utf8") as f:
        f.write(rad + "\n")


def text(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def schema_id(serie, datum, hemma, borta):
    h = hamta(f"https://stats.swehockey.se/ScheduleAndResults/Schedule/{serie}")
    d = None
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", h, flags=re.S):
        t = text(tr)
        m = re.search(r"(\d{4}-\d{2}-\d{2})", t)
        if m:
            d = m.group(1)
        gid = re.search(r"/Game/Events/(\d+)", tr)
        if gid and d == datum and hemma in t and borta in t:
            return gid.group(1)
    return None


idn, lineup_sparad = {}, set()
kandidater = json.loads(hamta("https://hockeyhype.se/data/live-kandidater.json"))["matcher"]
idag = datetime.date.today().isoformat()
kvall = [m for m in kandidater if m["tid"].startswith(idag) and not m["tid"].endswith("00:00")]
logg(f"start: {len(kvall)} matcher i kväll: " + ", ".join(f"{m['tid'][11:]} {m['hemma']}-{m['borta']}" for m in kvall))

while True:
    nu = datetime.datetime.now()
    hm = nu.strftime("%H:%M")
    if os.environ.get("START"):
        START = os.environ["START"]
    if hm > SLUT:
        break
    if hm < START:
        time.sleep(60)
        continue
    stamp = nu.strftime("%H%M")
    try:
        logg(f"{hm} api/live: " + hamta("https://hockeyhype.se/api/live"))
    except Exception as e:
        logg(f"{hm} api/live FEL {e}")
    for m in kvall:
        start = datetime.datetime.strptime(m["tid"], "%Y-%m-%d %H:%M")
        if not (start - datetime.timedelta(minutes=60) <= nu <= start + datetime.timedelta(minutes=200)):
            continue
        nyckel = (m["serie"], m["hemma"], m["borta"])
        try:
            if nyckel not in idn:
                gid = schema_id(m["serie"], idag, m["hemma"], m["borta"])
                if not gid:
                    logg(f"{hm}   {m['hemma']} - {m['borta']}: inget match-id i schemat än")
                    continue
                idn[nyckel] = gid
                logg(f"{hm}   {m['hemma']} - {m['borta']}: match-id {gid}")
            gid = idn[nyckel]
            h = hamta(f"https://stats.swehockey.se/Game/Events/{gid}")
            open(os.path.join(MAPP, f"events-{gid}-{stamp}.html"), "w", encoding="utf8").write(h)
            info = re.search(r'class="tdInfoArea"[^>]*>(.*?)</td>', h, flags=re.S)
            upd = (re.search(r"Last update:\s*([\d-]+ [\d:]+)", h) or [None, None])[1]
            tider = len(re.findall(r'>\s*\d{1,2}:\d{2}\s*</td>', h))
            logg(f"{hm}   {gid} {m['hemma']} - {m['borta']}: info='{text(info.group(1)) if info else ''}' "
                 f"lastupdate={upd} händelserader={tider} storlek={len(h)}")
            if gid not in lineup_sparad:
                l = hamta(f"https://stats.swehockey.se/Game/LineUps/{gid}")
                open(os.path.join(MAPP, f"lineup-{gid}-{stamp}.html"), "w", encoding="utf8").write(l)
                logg(f"{hm}   {gid} laguppställning: {len(l)} tecken")
                if len(l) > 5000:
                    lineup_sparad.add(gid)
        except Exception as e:
            logg(f"{hm}   {m['hemma']} - {m['borta']} FEL {e}")
    time.sleep(180)
logg("klart")
