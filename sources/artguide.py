"""Artforum's Artguide: the widest listing of NYC openings, with reception times.

The site is WordPress; its REST API serves every listing with the fields we need (reception date and
times, venue, neighborhood, coordinates, editors' "Must See" flag). The API can't filter by city, so
we page through everything published recently and keep New York.
"""
import datetime as dt

from .common import NEIGHBORHOODS, access, clean, get_json, opening, refreshments, split_artists, today

SOURCE = {"id": "artguide", "name": "Artforum Artguide", "url": "https://artguide.artforum.com/"}
API = "https://artguide.artforum.com/wp-json/wp/v2/ag-exhibition-event"
NEW_YORK = 60
# Galleries and nonprofits hold free openings; fairs and special events are usually ticketed.
VENUE_TYPES = {"Galleries", "Museums & Non-Profits"}
FIELDS = ",".join(["id", "link", "title", "card.image.original_url"] + ["meta." + f for f in (
    "location_id reception_date reception_start_time reception_end_time venue_name venue_slug "
    "venue_id venue_type_name neighborhood_name artists exhibition_name end_date latitude longitude "
    "is_must_see").split()])
LOOKBACK = 120  # days: listings are usually posted a few weeks before the opening


def fetch(days=14):
    first, last = today(), today() + dt.timedelta(days=days)
    after = (today() - dt.timedelta(days=LOOKBACK)).isoformat() + "T00:00:00"
    out, ids = [], []
    for page in range(1, 31):  # ~16 pages of 100 cover four months; stop at the first short page
        url = "%s?per_page=100&page=%d&after=%s&orderby=date&order=desc&_fields=%s" % (
            API, page, after, FIELDS)
        rows = get_json(url, timeout=30)
        for x in rows:
            m = x.get("meta") or {}
            if m.get("location_id") != NEW_YORK or not m.get("reception_date"):
                continue
            if clean(m.get("venue_type_name")) not in VENUE_TYPES:
                continue
            try:
                day = dt.date.fromisoformat(m["reception_date"])
            except ValueError:
                continue
            if not first <= day <= last:
                continue
            hood = clean(m.get("neighborhood_name"))
            ids.append(x["id"])
            out.append(opening(
                title=clean(x["title"]["rendered"]),
                venue=m.get("venue_name"),
                date=day,
                start=m.get("reception_start_time") or None,
                end=m.get("reception_end_time") or None,
                neighborhood=hood if hood in NEIGHBORHOODS else "",
                url=x.get("link"),
                venue_url=("https://artguide.artforum.com/venue/%s-%s/" % (m["venue_slug"], m["venue_id"])
                           if m.get("venue_slug") else None),
                closes=m.get("end_date") or None,
                lat=_f(m.get("latitude")), lng=_f(m.get("longitude")),
                pick=bool(m.get("is_must_see")),
                image=_thumb(((x.get("card") or {}).get("image") or {}).get("original_url")),
                artists=split_artists(m.get("artists")),
            ))
        if len(rows) < 100:
            break
    # Press releases are long, so they're fetched only for the openings we kept, to look for drinks
    # and RSVP requirements.
    texts = {}
    for i in range(0, len(ids), 100):
        rows = get_json("%s?per_page=100&include=%s&_fields=id,meta.press_release,meta.description" % (
            API, ",".join(map(str, ids[i:i + 100]))), timeout=30)
        for x in rows:
            m = x.get("meta") or {}
            texts[x["id"]] = (m.get("description") or "") + " " + (m.get("press_release") or "")
    for o, i in zip(out, ids):
        o["refreshments"] = refreshments(texts.get(i, ""))
        o["access"] = access(texts.get(i, ""))
    return out


def _thumb(url):
    return url.split("?")[0] + "?resize=240,240" if url else None


def _f(v):
    try:
        return round(float(v), 6)
    except (TypeError, ValueError):
        return None
