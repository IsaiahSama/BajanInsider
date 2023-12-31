# BajanInsider

Welcome to Bajan Insider.

## About

Bajan Insider is designed to act as a centralized location for all Barbados news.
Various stories will be pulled from various sources, organized, and then displayed on the site for your viewing convenience.

# Dev Notes for Me

## Technologies

I will be building this web app making use of React for the frontend, Flask for my backend, and SQLite for my database.

## Sources

Ideally, will just scour the internet for information related to Barbados news using a web crawler, but for now, will be targeting the following sites:

- https://www.nationnews.com
- https://barbadostoday.bb
- https://barbados.loopnews.com
- https://www.bbc.com/news/topics/cp7r8vgl2jxt
- https://www.barbadosadvocate.com

## Gathering of information

Currently, I have no clue. I'd have to examine the websites and see what patterns I can find, so I don't need to have unique code per website.

## Design

~~Currently, still have no clue. I'll do a wireframe after I get the scraping of at least one site working.~~

A wireframe is useful and all, but only if you know what you're doing. Currently, I have no idea what I'm doing, so the first step would be to break down the project into components, and then build from there.

### Components

The core component will be the Entry

#### Entry

    - Link (to the source)
    - Source (The name of the source)
    - Title (The title of the story)
    - Summary (The summary of the story.)

This Entry component will be a Card, containing the relevant information.

### Wireframe

[Here's the wireframe for the site.](https://wireframe.cc/hncWUP)

# Ending Notes

That's all for now. As I think of more things, and come across different issues and solutions, I'll update this document to suit.
