# Openings NYC

Free gallery openings in New York, night by night: who's opening, what time the reception is, and
where. It works well on a phone. It's the gallery version of
[showtimes-nyc](../showtimes-nyc).

## Run it

```
python3 server.py
```

Open http://localhost:8001. To use it on your phone, connect to the same Wi-Fi and open the
"On your phone" address the server prints. In Safari, tap Share → **Add to Home Screen** and it
opens full-screen like an app.

Listings are cached in `cache.json` and refreshed every hour, or right away when you tap Refresh.
`python3 server.py --once` scrapes everything once and prints what each source (and each gallery
website) found. That's the quickest way to see if a site has changed.

## Using it

- **Days** run from today through the next three weeks; the number under each day is how many
  openings it has. Thursday is the big night, especially in Chelsea.
- Openings are grouped by **neighborhood**, and each group has **Walk them all**, which opens Google
  Maps walking directions through every opening in that group, in time order.
- Tap ☆ to save an opening to **My night**. Saved openings live in your browser only.
- **+ Calendar** downloads an .ics file for that reception.
- **Reception not confirmed** means a gallery's show starts that day but the gallery hasn't posted a
  reception time yet. Most hold one 6–8pm on the first day; check closer to the date.

## Sources

| Source | What it gives | How |
| --- | --- | --- |
| [Artforum Artguide](https://artguide.artforum.com/) | Most listings: reception date and time, neighborhood, map position, editors' Must See picks | WordPress REST API (`sources/artguide.py`) |
| [artcards](https://artcards.cc/newyork) | A long-running NYC openings calendar; small these days | schema.org markup on the home page (`sources/artcards.py`) |
| Gallery websites on Artlogic | Upcoming shows straight from 18 galleries (Paula Cooper, Petzel, Tanya Bonakdar, Sean Kelly, P·P·O·W, James Cohan…), with the reception time from the press release when posted | `/exhibitions/` pages (`sources/artlogic.py`) |

Only galleries and nonprofits are listed. Art fairs and ticketed events are left out.

When two sources list the same gallery on the same night, they're merged into one stop. Artguide's
time and neighborhood win, a posted time beats a guessed one, and the gallery's own site wins on the
closing date.

Sources we tried and left out: ArtRabbit (blocks scripts), See Saw (no public listings site), and
e-flux (mostly museums and biennials, not openings with wine).

## Adding a gallery

If the gallery's site runs on Artlogic (its images load from `static-assets.artlogic.net`), add a
row to `GALLERIES` in `sources/artlogic.py` and run `python3 server.py --once` to check it finds
the shows. For any other site, add `sources/<id>.py` with a `SOURCE` dict and a `fetch(days)`
function (see the contract in `sources/common.py`), then add the id to `SOURCES` in `server.py`.

## Hosting it online (GitHub Pages)

`python3 build.py` scrapes everything and writes `static/data/openings.json`. The app uses the live
`api/` endpoint when `server.py` is running and otherwise falls back to that file, so `static/` can
be served by any plain web host.

`.github/workflows/refresh.yml` runs `build.py` on GitHub every three hours and publishes `static/`
to GitHub Pages. To turn it on: push this repository to GitHub, then in the repository's
**Settings → Pages**, set **Source** to **GitHub Actions**. To refresh by hand, open the **Actions**
tab → *Refresh openings* → **Run workflow**.

`python3 make_icons.py` re-renders the app icons from `static/logo.svg` (macOS only).

Requires only Python 3.9+, with no extra packages.
