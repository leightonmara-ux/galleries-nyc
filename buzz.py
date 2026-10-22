"""How anticipated an opening is, at a glance: a 0–3 "buzz" level with the reasons behind it.

Nobody publishes critics' expectations before a show opens, so buzz is pieced together from:
  - Artforum's editors flagging it Must See on Artguide          +3
  - the artist's Wikipedia page, by monthly page views          +3 (3,000+), +2 (800+), +1 (any page)
  - the gallery being one of the city's major galleries          +1
Levels: 4+ points → 3, 3 → 2, 1–2 → 1.

Wikipedia matches are kept only when the page describes an artist ("American portrait painter",
"Danish-Norwegian artist duo"), so a namesake politician doesn't make a show look famous.
"""
import json
import re
import urllib.parse
import urllib.request

WIKI = "https://en.wikipedia.org/w/api.php"
UA = "OpeningsNYC/1.0 (personal gallery listings app; stdlib urllib)"
ARTIST = re.compile(r"artist|painter|sculpt|photograph|printmaker|illustrat|ceramic|draft|draught|"
                    r"designer|filmmaker|video|install|mural|cartoon|duo|collective|potter|weaver|textile",
                    re.I)
BIG, KNOWN = 3000, 800  # monthly Wikipedia page views

# The galleries whose openings draw the art world; matched loosely against venue names.
MAJOR = """gagosian, david zwirner, hauser wirth, pace, gladstone, marian goodman, paula cooper,
matthew marks, david kordansky, sean kelly, petzel, lehmann maupin, 303, lisson, kasmin,
tanya bonakdar, luhring augustine, jack shainman, james cohan, ppow, andrew kreps, gavin brown,
perrotin, lgdr, white cube, thaddaeus ropac, sprueth magers, spruth magers, lelong, marianne boesky,
mitchell innes nash, casey kaplan, bortolami, anton kern, greene naftali, miguel abreu,
bridget donahue, canada, karma, sikkema malloy jenkins, salon 94, nicola vassell, grimm,
almine rech, alexander gray, fergus mccaffrey, yancey richardson, max hetzler, mendes wood,
nara roesler, tina kim, kordansky, matthew brown, hannah hoffman, jeffrey deitch, deitch"""
MAJOR_KEYS = [re.sub(r"[^a-z0-9]", "", g) for g in MAJOR.split(",")]


def lookup(names):
    """{name: {"title", "url", "description", "views"}} for the names that have an artist's page on
    English Wikipedia. Up to 50 names per request."""
    names = sorted({n for n in names if n})
    found = {}
    for i in range(0, len(names), 50):
        batch = names[i:i + 50]
        params = {"action": "query", "format": "json", "redirects": 1, "prop": "description|pageviews",
                  "pvipdays": 30, "titles": "|".join(batch)}
        # Wikipedia hands out page views for a few pages at a time; follow "continue" for the rest.
        d, cont = {}, {}
        for _ in range(20):
            req = urllib.request.Request(WIKI + "?" + urllib.parse.urlencode({**params, **cont}),
                                         headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                res = json.load(r)
            q = res.get("query", {})
            for k in ("normalized", "redirects"):
                d.setdefault(k, []).extend(x for x in q.get(k, []) if x not in d.get(k, []))
            for pid, p in q.get("pages", {}).items():
                old = d.setdefault("pages", {}).setdefault(pid, {})
                pv = {**(old.get("pageviews") or {}), **(p.get("pageviews") or {})}
                old.update({k: v for k, v in p.items() if v is not None})
                if pv:
                    old["pageviews"] = pv
            cont = res.get("continue")
            if not cont:
                break
        # Follow the name the way Wikipedia did: normalized spelling, then redirects.
        alias = {}
        for step in ("normalized", "redirects"):
            for x in d.get(step, []):
                alias[x["from"]] = x["to"]
        pages = {p["title"]: p for p in d.get("pages", {}).values() if "missing" not in p}
        for n in batch:
            t = n
            while t in alias:
                t = alias[t]
            p = pages.get(t)
            if not p or not ARTIST.search(p.get("description") or ""):
                continue
            views = sum(v or 0 for v in (p.get("pageviews") or {}).values())
            found[n] = {"title": t, "description": p["description"], "views": views,
                        "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"))}
    return found


def is_major(venue):
    k = re.sub(r"[^a-z0-9]", "", (venue or "").lower().replace("&", ""))
    return any(k.startswith(m) or (len(m) > 5 and m in k) for m in MAJOR_KEYS)


def score(stop, fame):
    """Sets stop["buzz"] (0–3), stop["reasons"] (short labels) and each show's "artists_info"."""
    pts, reasons = 0, []
    if stop.get("pick"):
        pts += 3
        reasons.append("Artforum must-see")
    best = None
    for sh in stop["shows"]:
        info = [dict(fame[a], name=a) for a in sh.get("artists", []) if a in fame]
        # A duo's page and its members' pages can both match; keep the best-known of each title.
        seen, uniq = set(), []
        for x in sorted(info, key=lambda x: -x["views"]):
            if x["title"] not in seen:
                seen.add(x["title"])
                uniq.append(x)
        sh["artists_info"] = uniq
        for x in uniq:
            if not best or x["views"] > best["views"]:
                best = x
    if best:
        if best["views"] >= BIG:
            pts += 3
            reasons.append("Big name")
        elif best["views"] >= KNOWN:
            pts += 2
            reasons.append("Known artist")
        else:
            pts += 1
            reasons.append("On Wikipedia")
    if is_major(stop["venue"]):
        pts += 1
        reasons.append("Major gallery")
    stop["buzz"] = 3 if pts >= 4 else 2 if pts >= 3 else 1 if pts >= 1 else 0
    stop["reasons"] = reasons
    stop["star_artist"] = best
    return stop
