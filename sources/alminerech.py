"""Almine Rech, Tribeca (361 Broadway). Its own site, not Artlogic:

    <li class="item item--exhibition"><a href="https://www.alminerech.com/exhibitions/12743-james-turrell">
      <img src="…cloudfront.net/rimage/pivot_photo_288/image/…"> <div class="tag">New York</div>
      <h3><span class="title">James Turrell</span><span class="subtitle">Show title</span></h3>
      <div class="info"> Nov 12, 2026 — Jan 30, 2027 </div></a></li>

The gallery has spaces in several cities; only New York listings are kept. Each upcoming show's page
is read for the reception time and any refreshments, as with the Artlogic galleries.
"""
import datetime as dt
import re

from .common import clean, get, opening, parse_date, parse_range, parse_time_range, refreshments, today, access as access_of

SOURCE = {"id": "alminerech", "name": "Almine Rech", "url": "https://www.alminerech.com/exhibitions"}
SITE = "https://www.alminerech.com"
RECEPTION = re.compile(r"[^.]*\b(?:reception|opening|join us)[^.]*\d[^.]*(?:[ap]\.?m\b)[^.]*", re.I)


def fetch(days=14):
    page = get(SITE + "/exhibitions")
    first, last = today(), today() + dt.timedelta(days=days)
    out, seen = [], set()
    for url, body in re.findall(r'<li class="item item--exhibition">\s*<a href="([^"]+)">(.*?)</a>\s*</li>', page, re.S):
        city = re.search(r'class="tag">(.*?)<', body)
        if url in seen or not city or clean(city.group(1)) != "New York":
            continue
        seen.add(url)
        start, end = parse_range(_g(r'class="info">(.*?)</div>', body))
        if not start or not first <= start <= last:
            continue
        artist, sub = _g(r'class="title">(.*?)</span>', body), _g(r'class="subtitle">(.*?)</span>', body)
        img = re.search(r'(https://[^"\s]*cloudfront\.net/rimage/)pivot_photo_\w+(/image/[^"\s]+)', body)
        day, t0, t1, confirmed, drinks, entry = start, None, None, False, None, None
        try:
            text = clean(re.sub(r"<script.*?</script>|<style.*?</style>", " ", get(url), flags=re.S))
            for sentence in RECEPTION.findall(text):
                a, b = parse_time_range(sentence)
                if a:
                    d = parse_date(sentence, start.year, start)
                    day = d if d and abs((d - start).days) <= 7 else start
                    t0, t1, confirmed = a, b, True
                    break
            drinks, entry = refreshments(text), access_of(text)
        except Exception:
            pass
        out.append(opening(
            title=": ".join(x for x in (artist, sub) if x), venue="Almine Rech", date=day, start=t0, end=t1,
            neighborhood="Tribeca / SoHo", address="361 Broadway", url=url, venue_url=SITE, closes=end,
            confirmed=confirmed, image=img.group(1) + "pivot_photo_288" + img.group(2) if img else None,
            artists=[artist] if artist else None, refreshments=drinks, access=entry))
    return out


def _g(pattern, s):
    m = re.search(pattern, s, re.S)
    return clean(m.group(1)) if m else ""
