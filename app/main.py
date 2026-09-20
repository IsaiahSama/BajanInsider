from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db.mongo_client import client
from app.models.news_collection import NewsCollection
from app.services.logger import get_logger
from app.services.misc import update_sitemap_lastmod
from app.services.summarize import summarize_latest_news

# Anchor filesystem paths on the package directory so the app starts from any
# working directory (the repo root or app/), not only from inside app/.
BASE_DIR = Path(__file__).resolve().parent

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Runs the one-off startup work before the app begins serving requests.

    Neither step is required to serve pages, so failures are logged and startup
    continues rather than letting a database outage take the web tier down.
    """
    try:
        update_sitemap_lastmod()
    except Exception:
        logger.exception(
            "Failed to update the sitemap lastmod date; continuing startup"
        )

    try:
        await client.ensure_indexes()
    except Exception:
        logger.exception(
            "Failed to ensure database indexes; continuing startup without them"
        )

    yield


app = FastAPI(lifespan=lifespan)

app.mount("/public", StaticFiles(directory=BASE_DIR / "public"), "public")

templates = Jinja2Templates(BASE_DIR / "templates")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/entries", response_model=NewsCollection, response_model_by_alias=False)
async def get_entries(start: int = 0, limit: int = 50):
    return await client.get_entries(start, limit)


# HTMX Routes

ENTRIES_PER_PAGE = 30


def paginate(total_entries: int, page: int) -> dict[str, int | bool]:
    """Builds the pagination context shared by the news feed partials.

    Args:
        total_entries (int): How many entries the feed can page through.
        page (int): The 1-based page being rendered.

    Returns:
        dict[str, int | bool]: `current_page`, `total_pages`, `has_next` and `has_prev`.
    """

    total_pages = (total_entries + ENTRIES_PER_PAGE - 1) // ENTRIES_PER_PAGE

    return {
        "current_page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


@app.get("/htmx/summary")
async def get_summary_htmx(request: Request):
    summary = await summarize_latest_news()
    return templates.TemplateResponse(
        request,
        "partials/summary.html",
        context={"summary": summary},
    )


@app.get("/htmx/entries")
async def get_entries_htmx(request: Request, page: int = 1):
    page = max(page, 1)  # page <= 0 would otherwise turn into a negative skip()
    start = (page - 1) * ENTRIES_PER_PAGE

    # Count instead of fetching every document just to size the pagination.
    total_entries = await client.count_entries()

    news_collection: NewsCollection | None = await client.get_entries(
        start, ENTRIES_PER_PAGE
    )
    entries = news_collection.entries if news_collection else []

    # Entries are passed as models and escaped by the template engine; never
    # pre-render them to strings here, that path bypassed autoescaping.
    return templates.TemplateResponse(
        request,
        "partials/news_entries_list.html",
        context={"entries": entries, "search": "", **paginate(total_entries, page)},
    )


@app.post("/htmx/entries/filter")
async def filter_entries_htmx(
    request: Request, search: Annotated[str, Form()] = "", page: int = 1
):
    # FastAPI treats an empty *required* form value as missing (422), so the
    # default is what lets clearing the search box fall back to the full feed.
    if not search:
        return await get_entries_htmx(request, page)

    filtered_news_collection: NewsCollection | None = await client.find_entry(search)
    matches = filtered_news_collection.entries if filtered_news_collection else []

    page = max(page, 1)
    start = (page - 1) * ENTRIES_PER_PAGE
    entries = matches[start : start + ENTRIES_PER_PAGE]

    # `search` goes back into the pagination links so that paging through a
    # search keeps filtering instead of falling back to the full feed.
    return templates.TemplateResponse(
        request,
        "partials/news_entries_list.html",
        context={
            "entries": entries,
            "search": search,
            **paginate(len(matches), page),
        },
    )


# Crawler files. Static assets are mounted under /public, but robots.txt and
# sitemap.xml are only honoured at the site root.

PUBLIC_DIR = BASE_DIR / "public"


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    return FileResponse(PUBLIC_DIR / "robots.txt", media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    return FileResponse(PUBLIC_DIR / "sitemap.xml", media_type="application/xml")
