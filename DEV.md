# Dev Notes for Me

Update: This project was originally done using React, Flask and SQLite. However, it is desperately in need of a rewrite.

## Technologies

Frontend: Jinja, HTMX, Bulma CSS
Server: FastAPI (Python)
Database: MongoDB

## Sources

News is read from each outlet's own syndication feed, never from a search engine. Feeds are stable, permitted, and cheap; `app/services/page_parser.py` holds one parser class per source and `app/services/scrape.py` lists which ones run.

Active sources (registered in `scrape.PARSERS`):

| Source | Parser | Feed URL | Format | Notes |
| --- | --- | --- | --- | --- |
| Nation News (nationnews.com) | `NationNewsParser` | `https://nationnews.com/feed/` | RSS 2.0 (WordPress) | Use the apex domain: the site's own `<link rel="alternate">` points there (`www.` is slower still). The origin is uncached behind Cloudflare and takes 20–30 s to send its first byte, so the parser sets `request_timeout = 60` instead of the 20 s default. `utm_*` link parameters and the WordPress "The post … appeared first on …" footer are stripped. |
| Barbados Today (barbadostoday.bb) | `BarbadosTodayParser` | `https://barbadostoday.bb/feed/` | RSS 2.0 (WordPress) | An Atom feed is also available at `/feed/atom/`; the parser accepts either. |
| BBC News, Barbados topic | `BBCBarbadosParser` | `https://feeds.bbci.co.uk/news/topics/cp7r8vgl2jxt/rss.xml` | RSS 2.0 | Links point at bbc.co.uk with `at_medium`/`at_campaign` analytics parameters, which are stripped. |

Dormant sources (implemented, kept in `scrape.DORMANT_PARSERS`, not fetched):

| Source | Parser | Last known feed URL | Format | Why dormant |
| --- | --- | --- | --- | --- |
| Loop News Barbados | `LoopNewsParser` | `https://www.loopnews.com/news/barbados/feed/` | RSS 2.0 (WordPress) | Digicel closed Loop News in July 2025. `barbados.loopnews.com` returns 404 and the relaunched `www.loopnews.com` serves an empty feed behind a TLS certificate that expired in February 2026. |
| The Barbados Advocate | `BarbadosAdvocateParser` | `https://www.barbadosadvocate.com/rss.xml` | RSS 2.0 (Drupal) | The paper ceased publication in 2023; the domain now redirects to an unrelated site with a mismatched certificate. |

If a dormant outlet comes back, move its class from `DORMANT_PARSERS` to `PARSERS`. No source currently needs an HTML fallback; if one ever lacks a feed, subclass `PageParser` directly and scrape its listing page with BeautifulSoup using shallow, semantic selectors (`article`, `h2 a`).

Adding a new source: subclass `RSSParser` in `page_parser.py`, set `source_name` (the label readers see) and `urls` (the feed URLs to fetch), then append the class to `PARSERS` in `scrape.py`. Capture one real response into `tests/fixtures/<source>.xml` and add it to `FIXTURE_FOR` in `tests/test_parsers.py`; the shared parametrised tests cover it from there. Only override `parse_entries` when a feed needs special handling.

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
