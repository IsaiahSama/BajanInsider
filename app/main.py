from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jinja2 import Template

from app.db.mongo_client import MongoClient
from app.models.news_collection import NewsCollection
from app.models.news_entry import NewsEntry

app = FastAPI()

templates = Jinja2Templates("templates")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


client = MongoClient()

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
async def get_entries(request: Request):
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
