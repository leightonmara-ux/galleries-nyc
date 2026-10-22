"""Galleries whose websites run on Artlogic, read straight from their /exhibitions pages.

Artlogic sites come in a few templates, and one parser handles them all (the main two):

  classic    <div id="exhibitions-grid-current|forthcoming"> … <li><a href="/exhibitions/962-…/">
             <h2>Artist: Title</h2><span class="subtitle">Gallery, New York</span>
             <span class="date">November 5 - December 18, 2026</span>
  Exhibit-E  <div class="entry"><a href="/exhibitions/james-little3"><div class="headers">
             <h1>Artist</h1><h2>Title</h2><h2 class="subtitle2">520 W 25th Street</h2>
             <h3>September 17 – October 31, 2026</h3>

A show's opening is its first day. For each show opening soon we read its page for the reception
("An opening reception will be held on Thursday, October 22 from 6–8PM"); when the page doesn't
say yet, the listing still shows, marked as unconfirmed.

To add a gallery, check that https://<site>/exhibitions/ lists shows in one of the two forms above,
then add a row to GALLERIES.
"""
import datetime as dt
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

from .common import clean, get, opening, parse_date, parse_range, parse_time_range, refreshments, today, access as access_of

SOURCE = {"id": "artlogic", "name": "Gallery websites", "url": "https://artlogic.net/"}

# id, name, website, neighborhood of the New York space
GALLERIES = [
    ("petzel", "Petzel", "https://www.petzel.com", "Chelsea"),
    ("paulacooper", "Paula Cooper Gallery", "https://www.paulacoopergallery.com", "Chelsea"),
    ("yancey", "Yancey Richardson", "https://www.yanceyrichardson.com", "Chelsea"),
    ("milesmcenery", "Miles McEnery Gallery", "https://www.milesmcenery.com", "Chelsea"),
    ("bonakdar", "Tanya Bonakdar Gallery", "https://www.tanyabonakdargallery.com", "Chelsea"),
    ("lelong", "Galerie Lelong", "https://www.galerielelong.com", "Chelsea"),
    ("boesky", "Marianne Boesky Gallery", "https://www.boeskygallery.com", "Chelsea"),
    ("hollistaggart", "Hollis Taggart", "https://www.hollistaggart.com", "Chelsea"),
    ("kasmin", "Kasmin", "https://www.kasmingallery.com", "Chelsea"),
    ("nararoesler", "Nara Roesler", "https://www.nararoesler.art", "Chelsea"),
    ("luhring", "Luhring Augustine", "https://www.luhringaugustine.com", "Chelsea"),
    ("seankelly", "Sean Kelly", "https://www.skny.com", "Midtown"),
    ("ppow", "P·P·O·W", "https://www.ppowgallery.com", "Tribeca / SoHo"),
    ("jamescohan", "James Cohan", "https://www.jamescohan.com", "Tribeca / SoHo"),
    ("kreps", "Andrew Kreps Gallery", "https://www.andrewkreps.com", "Tribeca / SoHo"),
    ("alexandergray", "Alexander Gray Associates", "https://www.alexandergray.com", "Tribeca / SoHo"),
    ("nicolavassell", "Nicola Vassell", "https://www.nicolavassell.com", "Chelsea"),
    ("tibordenagy", "Tibor de Nagy", "https://www.tibordenagy.com", "Downtown"),
    ("fortgansevoort", "Fort Gansevoort", "https://www.fortgansevoort.com", "Downtown"),
]
# A listing whose location line names one of these is at the gallery's other branch.
ELSEWHERE = re.compile(
    r"Los Angeles|London|Paris|S[ãa]o Paulo|Rio de Janeiro|Hong Kong|Seoul|Shanghai|Beijing|"
    r"Mexico|Berlin|Aspen|Palm Beach|Dublin|Tokyo|Taipei|Brussels|Milan|Rome|Zurich|Geneva|"
    r"Basel|Miami|Chicago|San Francisco|Southampton|East Hampton|Copenhagen|Singapore|Dubai", re.I)
RECEPTION = re.compile(r"[^.]*\b(?:reception|opening|join us|celebrat)[^.]*\d[^.]*(?:[ap]\.?m\b)[^.]*", re.I)


def fetch(days=14):
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda g: _gallery(g, days), GALLERIES))
    errors = [r for r in results if isinstance(r, Exception)]
    out = [o for r in results if not isinstance(r, Exception) for o in r]
    if errors and len(errors) == len(GALLERIES):
        raise errors[0]
    return out


def gallery_status(days=14):
    """Per-gallery counts, for `server.py --once`: (name, shows found, upcoming, error)."""
    rows = []
    for g in GALLERIES:
        try:
            shows = listings(g)
            rows.append((g[1], len(shows), len(_upcoming(shows, days)), None))
        except Exception as e:
            rows.append((g[1], 0, 0, "%s: %s" % (type(e).__name__, e)))
    return rows


def _gallery(g, days):
    try:
        return [_with_reception(g, s) for s in _upcoming(listings(g), days)]
    except Exception as e:
        return e


def _upcoming(shows, days):
    first, last = today(), today() + dt.timedelta(days=days)
    return [s for s in shows if s["start"] and first <= s["start"] <= last]


def listings(g):
    """Every show listed on the gallery's /exhibitions page: dicts with title, url, start, end, where."""
    gid, name, site, hood = g
    page = get(site + "/exhibitions/")
    shows = []
    # classic template
    for li in re.findall(r"<li[^>]*>\s*<a href=\"(/exhibitions/[^\"]+)\"[^>]*>(.*?)</a>\s*</li>", page, re.S):
        href, body = li
        h2 = re.search(r"<h2>(.*?)</h2>", body, re.S)
        date = re.search(r'<span class="date">(.*?)</span>', body, re.S)
        if not (h2 and date):
            continue
        where = re.search(r'<span class="subtitle">(.*?)</span>', body, re.S)
        shows.append(_show(site, href, clean(h2.group(1)), date.group(1), where and where.group(1), body))
    # Exhibit-E template
    for href, img, body in re.findall(r'<a href="(/exhibitions/[^"]+)">((?:(?!</a>).)*?)<div class="headers">(.*?)</div>',
                                      page, re.S):
        heads = re.findall(r"<(h[123])([^>]*)>(.*?)</\1>", body, re.S)
        artist = [clean(t) for h, a, t in heads if h == "h1"]
        titles = [clean(t) for h, a, t in heads if h == "h2" and "subtitle" not in a]
        where = [clean(t) for h, a, t in heads if "subtitle" in a]
        dates = [t for h, a, t in heads if h == "h3"]
        if not dates:
            continue
        if not titles and where and not re.search(r"\d", where[0]) and not ELSEWHERE.search(where[0]):
            titles, where = where[:1], where[1:]  # some sites put the show title in the subtitle
        title = ": ".join(x for x in (artist[:1] + titles[:1]) if x)
        shows.append(_show(site, href, title, dates[0], where[0] if where else "", img))
    # classic, list layout (Hollis Taggart): heading_title / location / dates spans
    for href, body in re.findall(r'<a href="(/exhibitions/[^"]+)">(.*?)</a>', page, re.S):
        title = re.search(r'class="heading_title">(.*?)</span>', body, re.S)
        date = re.search(r'class="dates[^"]*">(.*?)</div>', body, re.S)
        if title and date:
            where = re.search(r'class="location[^"]*">(.*?)</div>', body, re.S)
            shows.append(_show(site, href, clean(title.group(1)), date.group(1), where and where.group(1), body))
    seen, out = set(), []
    for s in shows:
        if s["url"] in seen or not s["title"] or (s["where"] and ELSEWHERE.search(s["where"])):
            continue
        seen.add(s["url"])
        out.append(s)
    return out


def _show(site, href, title, dates, where, markup=""):
    start, end = parse_range(clean(dates))
    return {"title": title, "url": urljoin(site + "/", href), "start": start, "end": end,
            "where": clean(where or ""), "image": _thumb(markup)}


def _thumb(markup):
    """The listing's image, resized by Artlogic's image server to a small square."""
    m = re.search(r'(https://static-assets\.artlogic\.net/)[^/\s"\']+(/[^\s"\']+?\.(?:jpe?g|png|webp))', markup or "", re.I)
    return m.group(1) + "w_240,h_240,c_lfill,q_auto" + m.group(2) if m else None


def _with_reception(g, s):
    gid, name, site, hood = g
    day, t0, t1, confirmed, drinks, entry = s["start"], None, None, False, None, None
    try:
        text = clean(re.sub(r"<script.*?</script>|<style.*?</style>", " ", get(s["url"]), flags=re.S))
        for sentence in RECEPTION.findall(text):
            a, b = parse_time_range(sentence)
            if not a:
                continue
            d = parse_date(sentence, s["start"].year, s["start"])
            if d and abs((d - s["start"]).days) <= 7:
                day = d
            t0, t1, confirmed = a, b, True
            break
        drinks, entry = refreshments(text), access_of(text)
    except Exception:
        pass  # the listing still shows, just without a confirmed time
    where = s["where"] if re.search(r"\d", s["where"]) else ""
    return opening(title=s["title"], venue=name, date=day, start=t0, end=t1, neighborhood=hood,
                   address=where, url=s["url"], venue_url=site, closes=s["end"], confirmed=confirmed,
                   image=s["image"], refreshments=drinks, access=entry)
