#!/usr/bin/env python3
"""Build a static copy of the app that any web host can serve, with no Python server behind it.

    python3 build.py

Scrapes every source and writes static/data/openings.json (what /api/openings returns). The app
tries the live /api/ endpoint first and falls back to that file, so the same static/ folder works
both behind server.py and on GitHub Pages (refreshed by .github/workflows/refresh.yml).
"""
import json

import server

OUT = server.STATIC


def main():
    data = server.scrape_all()
    (OUT / "data").mkdir(exist_ok=True)
    (OUT / "data" / "openings.json").write_text(json.dumps(server.public(data)))
    for s in data["sources"]:
        print("%-22s %4d openings  %s" % (s["name"], len(s["openings"]), s["error"] or ""))
    print("built static/: %d stops" % len(data["stops"]))
    # Artguide carries most of the listings; without it the page would look nearly empty.
    if not any(s["openings"] for s in data["sources"] if s["id"] == "artguide"):
        raise SystemExit("Artguide returned nothing; not publishing")


if __name__ == "__main__":
    main()
