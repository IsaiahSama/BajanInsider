# Dev Notes for Me

Update: This project was originally done using React, Flask and SQLite. However, it is desperately in need of a rewrite.

## Technologies

Frontend: Alpine, Jinja, HTMX, Bulma CSS
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
