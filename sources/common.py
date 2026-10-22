"""Shared helpers for opening sources (stdlib only, Python 3.9+).

Every source module exposes:

    SOURCE = {"id": ..., "name": ..., "url": ...}
    def fetch(days: int = 14) -> List[dict]

Each opening dict (build it with opening() so every field is present):
    title         str   show title, artists included when the source gives them
    venue         str   gallery name
    date          str   reception date, "YYYY-MM-DD"
    start, end    str   reception times "HH:MM" (24h), None when not posted
    neighborhood  str   one of NEIGHBORHOODS, or "" when unknown
    address       str   street address, "" when unknown
    url           str   the show's page (press release, images)
    venue_url     str   the gallery's website
    closes        str   last day of the show "YYYY-MM-DD", None when unknown
    confirmed     bool  True when the source says there's a reception; False when the date is
                        only the show's first day (galleries usually hold one that evening)
    lat, lng      float map position, None when unknown
    pick          bool  flagged by the source's editors (Artguide "Must See")
    image         str   a small image from the show (thumbnail size), None when there isn't one
    refreshments  str   what the gallery says it will serve ("Wine courtesy of …"), None if unsaid
    access        str   "rsvp" or "invite" when the gallery says so, "open" when it says all are
                        welcome, None when it says nothing (openings are walk-in by default)
    artists       list  artist names, when the source lists them separately; otherwise empty, and
                        artists_from_title() makes a guess
"""
import datetime as dt
import gzip
import html
import json
import re
import ssl
import urllib.request
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
NEIGHBORHOODS = ["Chelsea", "Tribeca / SoHo", "Downtown", "Midtown", "Uptown", "Upper West Side",
                 "Brooklyn", "Queens", "Bronx"]

# Rough ZIP -> neighborhood, for sources that only give an address.
_ZIPS = {
    "Chelsea": "10001 10011 10018",
    "Tribeca / SoHo": "10007 10012 10013 10014",
    "Downtown": "10002 10003 10004 10005 10006 10009 10038 10280",
    "Midtown": "10010 10016 10017 10019 10020 10022 10036",
    "Uptown": "10021 10028 10029 10065 10075 10128 10026 10027 10030 10031 10032 10035 10037 10039",
    "Upper West Side": "10023 10024 10025 10069",
}
ZIP_HOOD = {z: hood for hood, zs in _ZIPS.items() for z in zs.split()}


def get(url, headers=None, timeout=20, verify=True):
    """GET and return the decoded body. verify=False skips TLS checks (for sites with broken certs)."""
    h = {"User-Agent": UA, "Accept-Encoding": "gzip", "Accept-Language": "en-US,en;q=0.9"}
    h.update(headers or {})
    ctx = None if verify else ssl._create_unverified_context()
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        body = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        charset = r.headers.get_content_charset() or "utf-8"
        return body.decode(charset, errors="replace")


def get_json(url, **kw):
    return json.loads(get(url, **kw))


def now():
    return dt.datetime.now(NY).replace(tzinfo=None)


def today():
    return now().date()


def clean(s):
    """Strip tags, unescape entities, collapse whitespace."""
    if s is None:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def hood_for(address="", zipcode=""):
    """Neighborhood from a ZIP code (given, or found at the end of the address)."""
    z = zipcode or (re.findall(r"\b(1\d{4})\b", address or "") or [""])[-1]
    if z.startswith("112"):
        return "Brooklyn"
    if z.startswith("111") or z.startswith("113") or z.startswith("114"):
        return "Queens"
    if z.startswith("104"):
        return "Bronx"
    return ZIP_HOOD.get(z, "")


MONTHS = {m: i + 1 for i, m in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split())}


def parse_date(s, year=None, after=None):
    """'October 22' / 'Oct 22, 2026' / 'Thursday, October 22nd' -> date. Without a year, picks the
    one that puts the date closest to `after` (default today), so December listings read in January
    land in the right year."""
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b(?:,?\s+(\d{4}))?", s)
    if m and m.group(1)[:3].lower() in MONTHS:
        mon, day, y = m.group(1), m.group(2), m.group(3)
    else:  # day first: '15 October 2026'
        m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\b(?:,?\s+(\d{4}))?", s)
        if not m or m.group(2)[:3].lower() not in MONTHS:
            return None
        day, mon, y = m.group(1), m.group(2), m.group(3)
    mon, day = MONTHS[mon[:3].lower()], int(day)
    y = int(y) if y else year
    try:
        if y:
            return dt.date(y, mon, day)
        ref = after or today()
        cands = [dt.date(ref.year + k, mon, day) for k in (-1, 0, 1)]
        return min(cands, key=lambda d: abs((d - ref).days))
    except ValueError:
        return None


def parse_range(s, after=None):
    """'September 17 – October 31, 2026' / 'Nov 5 - Dec 18, 2026' / 'October 22 – 30, 2026'
    -> (start date, end date); either may be None."""
    s = clean(s).replace("–", "-").replace("—", "-")
    parts = re.split(r"\s+-\s+|\s*-\s*(?=[A-Za-z])|(?<=\d)\s*-\s*(?=\d)", s, maxsplit=1)
    years = re.findall(r"\b(20\d\d)\b", s)
    end_year = int(years[-1]) if years else None
    end = None
    if len(parts) == 2:
        p2 = parts[1]
        if re.match(r"^\d{1,2}(?:,?\s+\d{4})?$", p2.strip()):  # 'October 22 - 30, 2026'
            p2 = parts[0].split()[0] + " " + p2
        end = parse_date(p2, end_year, after)
    start_year = int(years[0]) if len(years) > 1 else (end.year if end else None)
    start = parse_date(parts[0], start_year, after)
    if start and end and start > end:  # 'December 4 - January 20, 2027'
        start = start.replace(year=start.year - 1)
    return start, end


_TIME = r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?)?"


def parse_time_range(s):
    """'6-8pm' / '6–8 PM' / '5:30–8:00 p.m.' / '6pm to 8pm' -> ('18:00', '20:00'); (None, None)."""
    s = (s or "").replace("–", "-").replace("—", "-")
    m = re.search(_TIME + r"\s*(?:-|to|until)\s*" + _TIME, s, re.I)
    if not m:
        m1 = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?)", s, re.I)
        if not m1:
            return None, None
        return _hm(m1.group(1), m1.group(2), m1.group(3), "p"), None
    ap2 = (m.group(6) or "p")
    end = _hm(m.group(4), m.group(5), ap2, "p")
    start = _hm(m.group(1), m.group(2), m.group(3) or ap2, "p")
    if start > end:  # '11-1pm' style: start is morning
        start = _hm(m.group(1), m.group(2), "a", "a")
    return start, end


def _hm(h, mi, ap, default):
    h, mi = int(h), int(mi or 0)
    ap = (ap or default).strip().lower()[:1]
    if ap == "p" and h != 12:
        h += 12
    if ap == "a" and h == 12:
        h = 0
    return "%02d:%02d" % (h, mi)


def opening(title, venue, date, start=None, end=None, neighborhood="", address="", url=None,
            venue_url=None, closes=None, confirmed=True, lat=None, lng=None, pick=False, image=None,
            artists=None, refreshments=None, access=None):
    return {"title": clean(title), "venue": clean(venue), "date": str(date),
            "start": start or None, "end": end or None, "neighborhood": neighborhood or "",
            "address": clean(address), "url": url or None, "venue_url": venue_url or None,
            "closes": str(closes) if closes else None, "confirmed": bool(confirmed),
            "lat": lat, "lng": lng, "pick": bool(pick), "image": image or None,
            "refreshments": refreshments or None, "access": access or None,
            "artists": artists or artists_from_title(title)}


NOT_NAMES = re.compile(r"\b(group|exhibition|show|collection|works|selected|new|recent|presents|"
                       r"paintings|drawings|sculpture|photographs|prints|years|art|and others)\b", re.I)


def artists_from_title(title):
    """'Kehinde Wiley: What the Light Becomes' -> ['Kehinde Wiley']; 'Andrew Weir & Jack Pierson' ->
    both; 'Teruko Yokoi "Seasons"' -> ['Teruko Yokoi']. Group shows and titles that don't look like
    names give []."""
    t = clean(title)
    head = re.split(r':|"|\u201c| \| | \u2013 | - ', t, maxsplit=1)[0].strip()
    return split_artists(head)


def split_artists(s):
    """'Andrew Weir & Jack Pierson' / 'A, B, and C' / 'Ward Shelley with Douglas Paulson' -> names.
    A duo's name ('Elmgreen & Dragset') is also kept whole, so it can be found as one entry."""
    s = clean(s)
    if not s or NOT_NAMES.search(s):
        return []
    parts = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+(?:and|with|&)\s+", s) if p.strip()]
    names = [p for p in parts if 1 <= len(p.split()) <= 4 and not re.search(r"\d", p)]
    if len(parts) == 2 and "&" in s:
        names.insert(0, s)
    return names[:4]


DRINKS = re.compile(r"\b(wine|champagne|prosecco|cocktails?|drinks|beverages|refreshments|beer|sake|mezcal|"
                    r"tequila|vodka|gin|spirits|bar\b|hors d|canap|bites|snacks|food|dumplings|oysters|"
                    r"sponsored by|courtesy of|poured by)", re.I)
NOT_DRINKS = re.compile(r"\b(painting|canvas|depict|still life|vineyard|bottle of|series|works? on|"
                        r"sculpture|photograph)", re.I)


def refreshments(text):
    """The sentence where a gallery says what it'll serve, trimmed: 'Drinks courtesy of Aperol.'
    Only sentences that also mention the opening, reception or event count, so a painting of a wine
    glass doesn't qualify."""
    for sentence in re.split(r"(?<=[.!?])\s+", clean(text)):
        if len(sentence) > 400 or not DRINKS.search(sentence) or NOT_DRINKS.search(sentence):
            continue
        if not re.search(r"reception|opening|event|evening|served|provided|join|celebrat|courtesy|sponsor|poured",
                         sentence, re.I):
            continue
        m = DRINKS.search(sentence)
        # Keep the part around the drinks mention, at most ~140 characters.
        start = max(0, sentence.rfind(",", 0, m.start()) + 1, m.start() - 80)
        snippet = sentence[start:start + 140].strip(" ,;")
        if start + 140 < len(sentence):
            snippet = snippet.rsplit(" ", 1)[0] + "…"
        return snippet[0].upper() + snippet[1:]
    return None


_INVITE = re.compile(r"by invitation|invitation only|invite[- ]only|private (?:view|reception|preview)", re.I)
_RSVP = re.compile(r"\bRSVP\b|registration (?:is )?required|register (?:here|in advance|to attend)|"
                   r"reserve (?:a|your) (?:spot|place|ticket)", re.I)
_OPEN = re.compile(r"(?:free and )?open to the public|all are welcome|everyone is welcome|no rsvp", re.I)


def access(text):
    """Whether the opening needs an RSVP or invitation, going by what the gallery wrote."""
    text = clean(text)
    if _OPEN.search(text) and not _INVITE.search(text):
        return "open"
    if _INVITE.search(text):
        return "invite"
    if _RSVP.search(text):
        return "rsvp"
    return None
