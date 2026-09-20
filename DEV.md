# Dev Notes for Me

Update: This project was originally done using React, Flask and SQLite. However, it is desperately in need of a rewrite.

## Technologies

Frontend: Jinja, HTMX, Bulma CSS
Server: FastAPI (Python)
Database: MongoDB

## Sources

Below is a list of the primary sites that will be used:

- https://www.nationnews.com
- https://barbadostoday.bb
- https://barbados.loopnews.com
- https://www.bbc.com/news/topics/cp7r8vgl2jxt
- https://www.barbadosadvocate.com

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
