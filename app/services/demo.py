import asyncio
from pprint import pprint

from bson import ObjectId

from app.db import MongoClient
from app.models.news_collection import NewsCollection
from app.models.news_entry import NewsEntry

from .page_parser import GoogleNewsParser
from .scraper import Scraper


async def add_entry_to_db(client: MongoClient, entry: NewsEntry):
    added_entry = await client.add_news_entry(entry)

    return added_entry


async def add_entries_to_db(client: MongoClient, entries: NewsCollection):
    await client.add_news_entries(entries)

    print("Added Entries")


async def view_one_entry(client: MongoClient, entry_id: str | ObjectId):
    result = await client.get_entry(entry_id)
    return result


async def view_all_entries(client: MongoClient):
    results = await client.get_all_entries()
    return results


async def main(entries: NewsCollection):
    client = MongoClient()

    pprint(f"{entries=}")

    print("Adding entry to db")
    entry = entries.entries.pop()

    added_entry = await add_entry_to_db(client, entry)

    if not added_entry:
        print("No entry was added")
        return

    print(added_entry)

    await add_entries_to_db(client, entries)

    print("Viewing one entry")

    if not added_entry.id:
        print("Can't get the ID. I fear we've failed...")
    else:
        pprint(await view_one_entry(client, added_entry.id))

    print("Viewing all entries")

    pprint(await view_all_entries(client))


if __name__ == "__main__":
    # Demo was made before Scraper was Async.
    # TODO: Update this!
    url = GoogleNewsParser.urls[0]
    soup = Scraper.get_soup(url)
    entries = Scraper.get_news(soup, GoogleNewsParser(), 10)

    if not entries:
        _ = input("Could not load entries")
        raise SystemExit

    asyncio.run(main(entries))
