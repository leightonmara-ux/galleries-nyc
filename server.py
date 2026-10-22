#!/usr/bin/env python3
"""NYC gallery openings: scrapes each source, merges them, caches the result, serves a mobile web app.

    python3 server.py            # http://localhost:8001 (and your LAN IP, for your phone)
    python3 server.py --once     # scrape once, print a summary, exit
"""
import argparse
import importlib
import json
import re
import socket
import threading
import time
import traceback
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from sources.common import now

ROOT = Path(__file__).parent
CACHE = ROOT / "cache.json"
STATIC = ROOT / "static"
# Listed first wins on conflicts: Artguide has the best times and neighborhoods.
SOURCES = ["artguide", "artcards", "artlogic"]
DAYS = 21  # how far ahead to list openings
TTL = 60 * 60  # seconds between refreshes

_lock = threading.Lock()
_data = None


def scrape_one(name):
    t0 = time.time()
    try:
        mod = importlib.import_module("sources." + name)
        found = mod.fetch(DAYS)
        return {**mod.SOURCE, "openings": found, "error": None, "secs": round(time.time() - t0, 1)}
    except Exception as e:
        traceback.print_exc()
        return {"id": name, "name": name, "openings": [], "error": "%s: %s" % (type(e).__name__, e),
                "secs": round(time.time() - t0, 1)}


def scrape_all():
    with ThreadPoolExecutor(len(SOURCES)) as ex:
        sources = list(ex.map(scrape_one, SOURCES))
    # Keep the previous good result for a source whose scrape failed this round.
    if _data:
        prev = {s["id"]: s for s in _data.get("sources", [])}
        for i, s in enumerate(sources):
            old = prev.get(s["id"])
            if s["error"] and old and old.get("openings"):
                sources[i] = {**old, "error": s["error"], "stale": True}
    data = {"updated": now().isoformat(timespec="minutes"), "fetched_at": time.time(),
            "sources": sources, "stops": merge(sources)}
    CACHE.write_text(json.dumps(data))
    return data


def key(s):
    """Loose form of a venue or show name for matching across sources."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = s.split("|")[0]
    s = re.sub(r"\b(the|gallery|galerie|galleries|associates|inc|llc|new york|nyc|fine arts?)\b", " ", s)
    return re.sub(r"[^a-z0-9]", "", s)


def words(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z0-9]{3,}", s)} - {"and", "the", "new", "works", "exhibition"}


def merge(sources):
    """One stop per gallery per night, each with the shows opening there. Fields from the first
    source that has them win, except that a posted reception time beats a guessed one."""
    stops = {}
    for src in sources:
        for o in src["openings"]:
            k = (key(o["venue"]), o["date"])
            st = stops.get(k)
            if st is None:
                venue = re.sub(r"\s*\|\s*New York\s*$", "", o["venue"]).replace(" | ", ", ")
                st = stops[k] = {"venue": venue, "date": o["date"], "start": o["start"],
                                 "end": o["end"], "confirmed": o["confirmed"],
                                 "neighborhood": o["neighborhood"], "address": o["address"],
                                 "venue_url": o["venue_url"], "lat": o["lat"], "lng": o["lng"],
                                 "pick": o["pick"], "sources": [], "shows": []}
            if o["start"] and (not st["start"] or not st["confirmed"]):
                st["start"], st["end"] = o["start"], o["end"]
            st["confirmed"] = st["confirmed"] or o["confirmed"]
            for f in ("neighborhood", "address", "lat", "lng"):
                st[f] = st[f] or o[f]
            # Prefer the gallery's own website over a listing-site venue page.
            if o["venue_url"] and (not st["venue_url"] or "artforum.com" in st["venue_url"]):
                st["venue_url"] = o["venue_url"]
            st["pick"] = st["pick"] or o["pick"]
            if src["id"] not in st["sources"]:
                st["sources"].append(src["id"])
            w = words(o["title"])
            same = next((sh for sh in st["shows"]
                         if w and len(w & words(sh["title"])) >= max(1, min(len(w), len(words(sh["title"]))) // 2)), None)
            if same:
                # The gallery's own site knows its closing date better than a listing site does.
                if o["closes"] and (not same["closes"] or src["id"] == "artlogic"):
                    same["closes"] = o["closes"]
                same.setdefault("links", [])
                if o["url"] and o["url"] not in same["links"] and o["url"] != same["url"]:
                    same["links"].append(o["url"])
            else:
                st["shows"].append({"title": o["title"], "url": o["url"], "closes": o["closes"], "links": []})
    return sorted(stops.values(), key=lambda s: (s["date"], s["start"] or "99", s["venue"].lower()))


def get_data(force=False):
    global _data
    with _lock:
        if _data is None and CACHE.exists():
            _data = json.loads(CACHE.read_text())
        if force or _data is None or time.time() - _data.get("fetched_at", 0) > TTL:
            _data = scrape_all()
        return _data


def public(data):
    """What the app gets: the stops plus a per-source summary (not the raw per-source lists)."""
    return {"updated": data["updated"], "stops": data["stops"],
            "sources": [{"id": s["id"], "name": s["name"], "url": s["url"], "count": len(s["openings"]),
                         "error": s["error"], "stale": s.get("stale", False)} for s in data["sources"]]}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(STATIC), **kw)

    def send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/openings"):
            data = public(get_data(force="refresh=1" in self.path))
            self.send(json.dumps(data).encode(), "application/json")
        else:
            super().do_GET()

    def end_headers(self):
        # Make browsers recheck the app's files, so an update shows up on the next load.
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(fmt, *args)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()
    if args.once:
        data = get_data(force=True)
        for s in data["sources"]:
            print("%-22s %4d openings  %5.1fs  %s" % (s["name"], len(s["openings"]), s["secs"], s["error"] or ""))
        print("%d stops after merging" % len(data["stops"]))
        from sources import artlogic
        for name, listed, upcoming, err in artlogic.gallery_status(DAYS):
            print("  %-28s %4d listed %3d opening soon  %s" % (name, listed, upcoming, err or ""))
        return
    threading.Thread(target=get_data, daemon=True).start()  # warm the cache
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print("Gallery openings running at http://localhost:%d" % args.port)
    ip = lan_ip()
    if ip:
        print("On your phone (same Wi-Fi):  http://%s:%d" % (ip, args.port))
    srv.serve_forever()


if __name__ == "__main__":
    main()
