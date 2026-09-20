from typing import Annotated
from fastapi import FastAPI, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import Template

from app.db.mongo_client import client
from app.models.news_collection import NewsCollection
from app.models.news_entry import NewsEntry
from app.services.summarize import summarize_latest_news
from app.services.misc import update_sitemap_lastmod
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from app.services.logger import get_logger

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
        logger.exception("Failed to update the sitemap lastmod date; continuing startup")

    try:
        await client.ensure_indexes()
    except Exception:
        logger.exception("Failed to ensure database indexes; continuing startup without them")

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


def render_partial(partial_name: str, context: dict[str, str | NewsEntry]) -> str:
    """Renders a partial template with the provided context.

    Args:
        partial_name (str): The name of the partial to render.
        context (dict[str, str]): The key value pairs to populate the template

    Returns:
        str: The rendered template as a string.
    """

    template_path = "templates/partials/" + partial_name + ".html"

    with open(template_path, "r") as file:
        template_content = file.read()
        template = Template(template_content)
        return template.render(**context)


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
    rendered_entries: list[str] = []
    ENTRIES_PER_PAGE = 30
    start = (page - 1) * ENTRIES_PER_PAGE

    # Get total count for pagination
    all_entries = await client.get_all_entries()
    total_entries = len(all_entries.entries) if all_entries else 0
    total_pages = (total_entries + ENTRIES_PER_PAGE - 1) // ENTRIES_PER_PAGE

    # Get paginated entries
    news_collection: NewsCollection | None = await client.get_entries(
        start, ENTRIES_PER_PAGE
    )

    if news_collection:
        for entry in news_collection.entries:
            rendered_entries.append(render_partial("news_entry", {"entry": entry}))

    return templates.TemplateResponse(
        request,
        "partials/news_entries_list.html",
        context={
            "entries": rendered_entries,
            "current_page": page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    )


@app.post("/htmx/entries/filter/")
async def filter_entries_htmx(
    request: Request, search: Annotated[str, Form()], page: int = 1
):
    rendered_entries: list[str] = []

    if not search:
        return await get_entries_htmx(request, page)

    filtered_news_collection: NewsCollection | None = await client.find_entry(search)

    if filtered_news_collection:
        ENTRIES_PER_PAGE = 30
        start = (page - 1) * ENTRIES_PER_PAGE
        end = start + ENTRIES_PER_PAGE
        total_entries = len(filtered_news_collection.entries)
        total_pages = (total_entries + ENTRIES_PER_PAGE - 1) // ENTRIES_PER_PAGE

        # Paginate the filtered entries
        paginated_entries = filtered_news_collection.entries[start:end]
        for entry in paginated_entries:
            rendered_entries.append(render_partial("news_entry", {"entry": entry}))

        return templates.TemplateResponse(
            request,
            "partials/news_entries_list.html",
            context={
                "entries": rendered_entries,
                "current_page": page,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        )

    return templates.TemplateResponse(
        request,
        "partials/news_entries_list.html",
        context={"entries": rendered_entries},
    )
