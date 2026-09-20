# Dev Notes for Me

Update: This project was originally done using React, Flask and SQLite. However, it is desperately in need of a rewrite.

## Technologies

Frontend: Jinja, HTMX, Bulma CSS
Server: FastAPI (Python)
Database: MongoDB

## Sources

News is read from syndication feeds, never scraped from a search engine's result pages: each outlet's own feed, plus the RSS feed Google News publishes for feed readers. Feeds are stable, permitted, and cheap; `app/services/page_parser.py` holds one parser class per source and `app/services/scrape.py` lists which ones run.

Active sources (registered in `scrape.PARSERS`):

| Source | Parser | Feed URL | Format | Notes |
| --- | --- | --- | --- | --- |
| Nation News (nationnews.com) | `NationNewsParser` | `https://nationnews.com/feed/` | RSS 2.0 (WordPress) | Use the apex domain: the site's own `<link rel="alternate">` points there (`www.` is slower still). The origin is uncached behind Cloudflare and takes 20–30 s to send its first byte, so the parser sets `request_timeout = 60` instead of the 20 s default. `utm_*` link parameters and the WordPress "The post … appeared first on …" footer are stripped. |
| Barbados Today (barbadostoday.bb) | `BarbadosTodayParser` | `https://barbadostoday.bb/feed/` | RSS 2.0 (WordPress) | An Atom feed is also available at `/feed/atom/`; the parser accepts either. |
| BBC News, Barbados topic | `BBCBarbadosParser` | `https://feeds.bbci.co.uk/news/topics/cp7r8vgl2jxt/rss.xml` | RSS 2.0 | Links point at bbc.co.uk with `at_medium`/`at_campaign` analytics parameters, which are stripped. |
| Google News, search feed for "barbados news" | `GoogleNewsRSSParser` | `https://news.google.com/rss/search?q=barbados+news&hl=en-GB&gl=GB&ceid=GB:en` | RSS 2.0 (aggregator) | The sanctioned RSS surface of Google News, published for feed readers. It replaces the project's original scraper of `google.com/search?tbm=nws` result pages, removed in September 2026 because it broke constantly and violated Google's ToS; never fetch or parse `google.com/search` or `news.google.com` HTML. Up to 100 items per fetch, so the parser sets `entries_per_url = 40` (the old scraper took 4 pages × 10) instead of the job default of 10. Registered last in `PARSERS` so the outlets' own feeds are launched first (see the comment there). |

Google News specifics. Google has no Barbados edition: `hl=en-BB&gl=BB&ceid=BB:en` is a 302 to the US edition. Of the two fallbacks, `en-GB` and `en-US` were equally relevant at capture (about 100/100 items about Barbados, ~70 of them from Barbados Today), so `en-GB` was chosen because its language matches the Barbadian English the site is written in and the `Accept-Language` the scraper already sends, and it surfaces more BBC/Guardian coverage and less US-domestic noise. The query stays `barbados news` (what the project used before); `q=barbados` alone returns mostly travel, cricket and air-quality pages (only ~12/100 items from Barbadian outlets). Items look like `<title>Headline - Publisher</title>` with a `<source>Publisher</source>` element, a `news.google.com/rss/articles/…` redirect as the link and a description that is only the headline again. The parser stores the `<source>` text as `source` and strips the ` - Publisher` suffix from the title, so a story Google surfaces from an outlet that is already a first-party source has the same `(title, source, date_scraped)` key and is dropped by the unique index (Google labels the BBC as "BBC", not "BBC News", so those two do not collapse). The redirect link is kept as-is (it resolves in a browser; decoding it offline is unreliable) and `content` is empty. Tuning knob: `when:2d` inside `q` (`q=barbados+news+when:2d`) limits the feed to the last two days, roughly 40–50 items at capture; it is off because the job runs twice a day and the index dedupes across runs.

Dormant sources (implemented, kept in `scrape.DORMANT_PARSERS`, not fetched):

| Source | Parser | Last known feed URL | Format | Why dormant |
| --- | --- | --- | --- | --- |
| Loop News Barbados | `LoopNewsParser` | `https://www.loopnews.com/news/barbados/feed/` | RSS 2.0 (WordPress) | Digicel closed Loop News in July 2025. `barbados.loopnews.com` returns 404 and the relaunched `www.loopnews.com` serves an empty feed behind a TLS certificate that expired in February 2026. |
| The Barbados Advocate | `BarbadosAdvocateParser` | `https://www.barbadosadvocate.com/rss.xml` | RSS 2.0 (Drupal) | The paper ceased publication in 2023; the domain now redirects to an unrelated site with a mismatched certificate. |

If a dormant outlet comes back, move its class from `DORMANT_PARSERS` to `PARSERS`. No source currently needs an HTML fallback; if one ever lacks a feed, subclass `PageParser` directly and scrape its listing page with BeautifulSoup using shallow, semantic selectors (`article`, `h2 a`).

Adding a new source: subclass `RSSParser` in `page_parser.py`, set `source_name` (the label readers see) and `urls` (the feed URLs to fetch), then append the class to `PARSERS` in `scrape.py`. Capture one real response into `tests/fixtures/<source>.xml` and add it to `FIXTURE_FOR` in `tests/test_parsers.py`; the shared parametrised tests cover it from there. Set `entries_per_url` only when a feed should contribute more or fewer entries than the job default (`scrape.ENTRIES_PER_URL`, 10). Only override `parse_entries` when a feed needs special handling; an aggregator whose items come from many outlets overrides the `RSSParser` per-item hooks (`_rss_item_title_and_source`, `_rss_item_content`) instead, as `GoogleNewsRSSParser` does.

## Gathering of information

Information will be gathered every morning by way of a web crawler.

## Design

I use [wireframe.cc](https://wireframe.cc) for my wireframes. However, as anyone can modify it, I have simply included an image in the root folder as `wireframe.png`.

### Components

This section details the components that will be used in the building of the application.

These components are:

- NewsEntry
- NewsEntryPartial

#### Entry

This component will be the main one, and represents a news entry as scraped from it's source. It will be made up of the following attributes:

    - ID (An ID to use to uniquely identify)
    - Title (The title of the story)
    - Content (A snippet of the story as scraped)
    - Source (The name of the source)
    - DateScraped (The date that the entry was scraped)
    - Link (to the source)

This website will only have snippets of the story, so as to not take traffic away from the source sites.

# Ending Notes

That's all for now. As I think of more things, and come across different issues and solutions, I'll update this document to suit.

## Deduplication

A story is stored once. Two unique indexes on `news_entry` define "the same story":

1. `link` — the article URL. Catches the same item re-offered by a feed on later
   days (feeds keep items for days or weeks) and headline edits.
2. `(title, source)`, case-insensitive — catches aggregator copies (Google News)
   whose link is a redirect rather than the publisher URL.

`date_scraped` is not part of the identity. Publisher labels are canonicalised at
parse time via `SOURCE_ALIASES` in `app/services/page_parser.py` so one outlet has
one name ("BBC" → "BBC News"); add a row there when a new spelling appears.
Title alone is deliberately *not* the identity: different outlets' own articles
under the same headline are different stories.

The outlets' own feeds (`PRIMARY_PARSERS`) are fetched and stored before any
aggregator (`AGGREGATOR_PARSERS`), so the copy kept is the one with a snippet and
the publisher's link. Barbados Today's feed is read four pages deep for the same
reason. When an outlet's copy is rejected as a duplicate of a stored copy that has
no snippet (an earlier Google copy), the snippet, link and publish time are
backfilled onto the stored document.

## Ordering

The feed is newest first by the publisher's own timestamp (`published_at`, from
`pubDate` / Atom `published`), falling back to when we stored the entry
(`created_at`) and, for rows older than that field, to `date_scraped`. Entries
without a feed date are never given an invented one.

## Running & testing

### Environment variables

Copy `app/.env.example` to `app/.env` (it is loaded automatically on import) or export the variables in your shell:

| Variable | Purpose |
| --- | --- |
| `MONGODB_URL` | MongoDB connection string. Required. |
| `GEMINI_API_KEY` | Google Gemini API key used for the AI summary. Required. |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. Defaults to `INFO`. Set `LOGGING=false` to silence logging entirely. |

### Install

The project is managed with [uv](https://docs.astral.sh/uv/). Install the runtime and dev dependencies (pytest, ruff, pyright, httpx) with:

```sh
uv sync --group dev
```

`requirements.txt` is generated from `uv.lock` for hosts that install with pip. Regenerate it after changing dependencies:

```sh
uv lock
uv export --no-dev --no-hashes --format requirements-txt -o requirements.txt
```

### Run the server

Today `app.main` resolves `public/` and `templates/` relative to the current directory, so run it from inside `app/` with the repo root on the import path:

```sh
cd app && PYTHONPATH=.. uv run uvicorn app.main:app --reload
```

That working-directory requirement is being removed; once it is, `uv run uvicorn app.main:app --reload` from the repo root will work.

### Run the scraper

```sh
uv run python -m app.services.scrape
```

### Tests, lint and types

```sh
uv run pytest
uv run ruff check .
uv run pyright
```

Tests need `MONGODB_URL` and `GEMINI_API_KEY` set (any value works; the database is mocked and no Mongo server is required). `tests/conftest.py` fills in dummy values when they are absent.

### Tailwind build

The stylesheet at `app/public/css/app.css` is built from `app/tailwindcss/`:

```sh
cd app/tailwindcss && npm install && npm run dev
```
