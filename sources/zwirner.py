"""David Zwirner. The site is Next.js; the /exhibitions page embeds its data as JSON in
<script id="__NEXT_DATA__">, under props.pageProps.data.upcoming / nowOpen. Each show has
startDate, endDate, a "reception" string ("Thursday, November 5, 6–8 PM"), its artists, its
locations (with street address and ZIP) and a Sanity image asset id.
"""
import datetime as dt
import json
import re

from .common import (access, clean, get, hood_for, opening, parse_date, parse_time_range,
                     refreshments, today)

SOURCE = {"id": "zwirner", "name": "David Zwirner", "url": "https://www.davidzwirner.com/exhibitions"}
SITE = "https://www.davidzwirner.com"


def fetch(days=14):
    page = get(SITE + "/exhibitions")
    data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S).group(1))
    data = data["props"]["pageProps"]["data"]
    cdn = re.search(r"cdn\.sanity\.io/images/([a-z0-9]+/[a-z0-9-]+)/", page)
    first, last = today(), today() + dt.timedelta(days=days)
    out, seen = [], set()
    for x in (data.get("upcoming") or []) + (data.get("nowOpen") or []):
        nyc = [l for l in x.get("locations") or [] if (l.get("name") or "").startswith("New York")]
        if x["_id"] in seen or not nyc or not x.get("startDate"):
            continue
        seen.add(x["_id"])
        start = dt.date.fromisoformat(x["startDate"])
        rec = x.get("reception") or ""
        day = parse_date(rec, start.year, start) or start
        if not first <= day <= last:
            continue
        t0, t1 = parse_time_range(rec)
        addr = (nyc[0].get("address") or {})
        url = SITE + ((x.get("slug") or {}).get("current") or "")
        drinks = entry = None
        try:
            text = clean(re.sub(r"<script.*?</script>", " ", get(url), flags=re.S))
            drinks, entry = refreshments(text), access(text)
        except Exception:
            pass
        artists = [a.get("fullName") for a in x.get("artists") or [] if a.get("fullName")]
        out.append(opening(
            title=": ".join(t for t in (x.get("title"), x.get("subtitle")) if t),
            venue="David Zwirner", date=day, start=t0, end=t1,
            neighborhood=hood_for(zipcode=addr.get("zipCode") or ""),
            address=addr.get("addressLine") or "", url=url, venue_url=SITE,
            closes=x.get("endDate"), confirmed=bool(rec), image=_image(x, cdn),
            artists=artists or None, refreshments=drinks, access=entry))
    return out


def _image(x, cdn):
    """Sanity asset ids look like image-<hash>-3000x1688-jpg; the CDN serves <hash>-3000x1688.jpg."""
    asset = (((x.get("cardViewMedia") or {}).get("image") or {}).get("_id") or "")
    m = re.match(r"image-([0-9a-f]+-\d+x\d+)-(\w+)$", asset)
    if not (m and cdn):
        return None
    return "https://cdn.sanity.io/images/%s/%s.%s?w=240&h=240&fit=crop" % (cdn.group(1), m.group(1), m.group(2))
