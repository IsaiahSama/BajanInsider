from typing import Annotated
from fastapi import FastAPI, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import Template

from app.db.mongo_client import MongoClient
from app.models.news_collection import NewsCollection
from app.models.news_entry import NewsEntry

app = FastAPI()

app.mount("/public", StaticFiles(directory="public"), "public")

templates = Jinja2Templates("templates")

client = MongoClient()


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


@app.get("/htmx/entries")
async def get_entries_htmx(request: Request):
    rendered_entries: list[str] = []

    news_collection: NewsCollection | None = await client.get_all_entries()

    if news_collection:
        for entry in news_collection.entries:
            rendered_entries.append(render_partial("news_entry", {"entry": entry}))

    return templates.TemplateResponse(
        request,
        "partials/news_entries_list.html",
        context={"entries": rendered_entries},
    )


@app.post("/htmx/entries/filter/")
async def filter_entries_htmx(request: Request, search: Annotated[str, Form()]):
    rendered_entries: list[str] = []

    if not search:
        return await get_entries_htmx(request)

    filtered_news_collection: NewsCollection | None = await client.find_entry(search)

    if filtered_news_collection:
        for entry in filtered_news_collection.entries:
            rendered_entries.append(render_partial("news_entry", {"entry": entry}))

    return templates.TemplateResponse(
        request,
        "partials/news_entries_list.html",
        context={"entries": rendered_entries},
    )
