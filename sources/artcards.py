"""artcards.cc: a long-running NYC openings calendar. Small these days, but every listing is an
opening with a time. Its certificate is self-signed, hence verify=False.

Each listing is schema.org Event microdata:
    <section><h1>Thursday, October 22</h1>
      <article itemtype="http://schema.org/Event"><span itemprop="name">Artist "Show"</span> at
        <div itemprop="location"><a itemprop="url" href="gallery site"><span itemprop="name">Gallery</span></a>
        <a class="map-link">26 street: 521 W 26th Street</a>, <time>6-8pm</time>
        <meta itemprop="streetAddress" ...><meta itemprop="postalCode" ...></div>
        <a href="artcards show page" class="comment">…<meta itemprop="startDate" content="2026-10-22">
"""
import datetime as dt
import re

from .common import clean, get, hood_for, opening, parse_time_range, today

SOURCE = {"id": "artcards", "name": "artcards", "url": "https://artcards.cc/newyork"}


def fetch(days=14):
    page = get("https://artcards.cc/", verify=False)
    last = today() + dt.timedelta(days=days)
    out = []
    for art in re.findall(r'<article[^>]*schema.org/Event[^>]*>(.*?)</article>', page, re.S):
        date = re.search(r'itemprop="startDate" content="(\d{4}-\d\d-\d\d)"', art)
        if not date:
            continue
        day = dt.date.fromisoformat(date.group(1))
        if not today() <= day <= last:
            continue
        title = re.search(r'<span itemprop="name">(.*?)</span>', art, re.S)
        loc = re.search(r'itemprop="location".*?<a itemprop="url" href="([^"]*)"[^>]*>\s*'
                        r'<span itemprop="name">(.*?)</span>', art, re.S)
        street = re.search(r'itemprop="streetAddress" content="([^"]*)"', art)
        zipcode = re.search(r'itemprop="postalCode" content="([^"]*)"', art)
        when = re.search(r"<time>(.*?)</time>", art)
        page_url = re.search(r'href="([^"]*)" class="comment"', art)
        start, end = parse_time_range(when.group(1) if when else "")
        out.append(opening(
            title=clean(title.group(1)) if title else "",
            venue=loc.group(2) if loc else "",
            date=day, start=start, end=end,
            address=street.group(1) if street else "",
            neighborhood=hood_for(zipcode=zipcode.group(1) if zipcode else ""),
            url=page_url.group(1) if page_url else None,
            venue_url=loc.group(1) if loc else None,
        ))
    return out
