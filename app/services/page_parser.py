"""Per-source news parsers.

Every news source is a :class:`PageParser` subclass that turns the raw text of a fetched
page into a :class:`~app.models.news_collection.NewsCollection`. Feeds (RSS 2.0 / Atom) are
the preferred input and are handled generically by :class:`RSSParser`; a source without a
feed would subclass :class:`PageParser` directly and scrape its listing HTML with bs4.

To add a source: subclass :class:`RSSParser` (or :class:`PageParser`), set ``source_name``
and ``urls``, then register the class in ``app.services.scrape.PARSERS``.
"""

import html
import re
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import ClassVar, override
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.models.news_collection import NewsCollection
from app.models.news_entry import NewsEntry

from .logger import get_logger

logger = get_logger(__name__)

SNIPPET_MAX_CHARS = 500
"""Snippets are capped so the site sends readers to the source for the full story."""

ELLIPSIS = "…"

_TAG_RE = re.compile(r"<[^>]*>")
_WHITESPACE_RE = re.compile(r"\s+")
_XML_DECLARATION_RE = re.compile(r"^\s*<\?xml[^>]*\?>")
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = frozenset({"at_medium", "at_campaign"})  # BBC feed analytics


# --------------------------------------------------------------------------- text helpers


def strip_html(text: str) -> str:
    """Return the visible text of an HTML fragment.

    Tags are removed, character references are unescaped and runs of whitespace are
    collapsed to single spaces.

    Args:
        text: An HTML fragment, or plain text.

    Returns:
        The cleaned text, stripped of surrounding whitespace.
    """
    without_tags = _TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", html.unescape(without_tags)).strip()


def truncate(text: str, limit: int = SNIPPET_MAX_CHARS) -> str:
    """Shorten ``text`` to about ``limit`` characters, cutting on a word boundary.

    Args:
        text: The text to shorten.
        limit: The maximum number of characters to keep before the ellipsis.

    Returns:
        ``text`` unchanged when it fits, otherwise the leading words plus an ellipsis.
    """
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit + 1)
    if cut <= 0:
        cut = limit
    return text[:cut].rstrip(" ,;:") + ELLIPSIS


def normalise_link(href: str | None, base_url: str) -> str | None:
    """Turn a feed link into an absolute ``http(s)`` URL without tracking parameters.

    Args:
        href: The raw link text or attribute, possibly relative or empty.
        base_url: The URL to resolve relative links against.

    Returns:
        The cleaned absolute URL, or ``None`` when the link is unusable.
    """
    if not href:
        return None
    absolute = urljoin(base_url, html.unescape(href.strip()))
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def today() -> str:
    """The local calendar date as ``YYYY-MM-DD``, the ``date_scraped`` convention app-wide."""
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d")


def _is_tracking_param(key: str) -> bool:
    return key.startswith(_TRACKING_PARAM_PREFIXES) or key in _TRACKING_PARAMS


def _strip_wordpress_footer(text: str) -> str:
    """Drop WordPress' trailing "The post <title> appeared first on <site>." from an excerpt."""
    start = text.rfind("The post ")
    if start != -1 and " appeared first on " in text[start:]:
        return text[:start].rstrip()
    return text


def _parse_published(raw: str) -> datetime | None:
    """Parse an RFC 822 (RSS) or ISO 8601 (Atom) timestamp, or return ``None``."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


# --------------------------------------------------------------------------- XML helpers


def _local_name(tag: str) -> str:
    """Strip the ``{namespace}`` prefix ElementTree puts on qualified tags."""
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> Iterator[ET.Element]:
    return (child for child in element if _local_name(child.tag) == name)


def _first_child(element: ET.Element, name: str) -> ET.Element | None:
    return next(_children(element, name), None)


def _child_text(element: ET.Element, name: str) -> str:
    """Text of the first child called ``name`` (any namespace) that has any, else ``""``."""
    for child in _children(element, name):
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def _atom_alternate_href(element: ET.Element) -> str | None:
    """The ``href`` of the first ``<link>`` child that points at the story itself."""
    for link in _children(element, "link"):
        href = (link.get("href") or "").strip()
        if href and link.get("rel", "alternate") == "alternate":
            return href
    return None


def _permalink_guid(item: ET.Element) -> str | None:
    """An RSS ``<guid>`` doubles as the link unless it says ``isPermaLink="false"``."""
    guid = _first_child(item, "guid")
    if guid is None:
        return None
    text = (guid.text or "").strip()
    is_permalink = guid.get("isPermaLink", "true").lower() != "false"
    return text if is_permalink and text.startswith(("http://", "https://")) else None


def _parse_xml(text: str, parser_name: str) -> ET.Element | None:
    """Parse feed text into an element tree, logging (not raising) on bad input.

    The XML declaration is dropped first: the body has already been decoded to ``str`` by
    the HTTP client, so a declared encoding would only confuse the parser.
    """
    cleaned = _XML_DECLARATION_RE.sub("", text.lstrip("﻿"), count=1)
    if not cleaned.strip():
        logger.warning("%s: empty response body", parser_name)
        return None
    try:
        return ET.fromstring(cleaned)
    except (ET.ParseError, ValueError) as error:
        logger.warning("%s: response is not well-formed XML: %s", parser_name, error)
        return None


# --------------------------------------------------------------------------- base classes


class PageParser(ABC):
    """Base class for one news source.

    Subclasses set ``source_name`` (shown to readers) and ``urls`` (pages fetched each run)
    and implement :meth:`parse_entries`. The helpers on this class apply the same rules to
    every source: titles are unescaped and whitespace-normalised, links are absolute and
    free of tracking parameters, snippets are tag-free and capped at
    :data:`SNIPPET_MAX_CHARS`, and an item without a title or link is skipped.
    """

    source_name: ClassVar[str]
    urls: ClassVar[list[str]]
    request_timeout: ClassVar[float | None] = None
    """Total seconds allowed per request, for slow origins; ``None`` uses the Scraper default."""

    @classmethod
    @abstractmethod
    def parse_entries(cls, text: str, n: int) -> NewsCollection | None:
        """Turn the raw text of a fetched page into news entries.

        Args:
            text: The response body exactly as fetched (feed XML or HTML).
            n: The maximum number of entries to return.

        Returns:
            A collection of at most ``n`` entries with unique links, or ``None`` when
            nothing usable could be parsed.
        """
        raise NotImplementedError

    @classmethod
    def base_url(cls) -> str:
        """The URL relative links are resolved against when the page gives no better one."""
        urls: list[str] = getattr(cls, "urls", [])
        return urls[0] if urls else ""

    @classmethod
    def build_entry(
        cls,
        *,
        title: str | None,
        link: str | None,
        content: str | None,
        base_url: str,
    ) -> NewsEntry | None:
        """Validate and normalise one item's fields into a :class:`NewsEntry`.

        Args:
            title: Raw title text (may contain markup or character references).
            link: Raw link, absolute or relative.
            content: Raw description/summary HTML; ``None`` or empty gives an empty snippet.
            base_url: The URL relative links are resolved against.

        Returns:
            The entry, or ``None`` when the title or link is missing or unusable.
        """
        clean_title = strip_html(title or "")
        if not clean_title:
            logger.debug(
                "%s: skipping item without a title (link=%r)", cls.__name__, link
            )
            return None
        clean_link = normalise_link(link, base_url)
        if clean_link is None:
            logger.debug(
                "%s: skipping %r, no usable link (%r)", cls.__name__, clean_title, link
            )
            return None
        snippet = truncate(_strip_wordpress_footer(strip_html(content or "")))
        return NewsEntry(
            title=clean_title,
            content=snippet,
            source=cls.source_name,
            link=clean_link,
            date_scraped=today(),
        )

    @classmethod
    def collect(
        cls, entries: Iterable[NewsEntry | None], n: int
    ) -> NewsCollection | None:
        """Keep the first ``n`` entries with distinct links, dropping ``None`` placeholders.

        Args:
            entries: Candidate entries in feed order; ``None`` marks a skipped item.
            n: The maximum number of entries to keep.

        Returns:
            The collection, or ``None`` when no entry survived.
        """
        kept: list[NewsEntry] = []
        seen_links: set[str] = set()
        for entry in entries:
            if len(kept) >= n:
                break
            if entry is None or entry.link in seen_links:
                continue
            seen_links.add(entry.link)
            kept.append(entry)
        if not kept:
            logger.warning("%s: no entries parsed", cls.__name__)
            return None
        return NewsCollection(entries=kept)


class RSSParser(PageParser):
    """Parser for RSS 2.0, RSS 1.0 (RDF) and Atom feeds, using the stdlib ElementTree.

    Most sources need nothing beyond ``source_name`` and ``urls``. Element names are matched
    without regard to namespace, CDATA is transparent, and missing fields degrade
    gracefully: no title or link skips the item, no description gives an empty snippet.
    Malformed XML is logged and yields ``None`` rather than an exception.
    """

    @classmethod
    @override
    def parse_entries(cls, text: str, n: int) -> NewsCollection | None:
        if n <= 0:
            return None
        root = _parse_xml(text, cls.__name__)
        if root is None:
            return None

        kind = _local_name(root.tag)
        if kind in {"rss", "RDF"}:
            channel = _first_child(root, "channel")
            base_url = _child_text(channel if channel is not None else root, "link")
            items = (el for el in root.iter() if _local_name(el.tag) == "item")
            entries = (
                cls._rss_item(item, base_url or cls.base_url()) for item in items
            )
        elif kind == "feed":
            base_url = _atom_alternate_href(root) or cls.base_url()
            entries = (
                cls._atom_entry(entry, base_url) for entry in _children(root, "entry")
            )
        else:
            logger.warning("%s: unrecognised feed root <%s>", cls.__name__, kind)
            return None
        return cls.collect(entries, n)

    @classmethod
    def _rss_item(cls, item: ET.Element, base_url: str) -> NewsEntry | None:
        """Build an entry from an RSS ``<item>``."""
        title = _child_text(item, "title")
        link = (
            _child_text(item, "link")
            or _atom_alternate_href(item)
            or _permalink_guid(item)
        )
        description = _child_text(item, "description")
        # WordPress and Drupal sometimes put only an image in the excerpt; fall back to
        # the full body (content:encoded) so the snippet has something to show.
        content = (
            description if strip_html(description) else _child_text(item, "encoded")
        )
        cls._log_published(
            title, _child_text(item, "pubDate") or _child_text(item, "date")
        )
        return cls.build_entry(
            title=title, link=link, content=content, base_url=base_url
        )

    @classmethod
    def _atom_entry(cls, entry: ET.Element, base_url: str) -> NewsEntry | None:
        """Build an entry from an Atom ``<entry>``."""
        title = _child_text(entry, "title")
        link = _atom_alternate_href(entry)
        content = _child_text(entry, "summary") or _child_text(entry, "content")
        cls._log_published(
            title, _child_text(entry, "published") or _child_text(entry, "updated")
        )
        return cls.build_entry(
            title=title, link=link, content=content, base_url=base_url
        )

    @classmethod
    def _log_published(cls, title: str, raw_date: str) -> None:
        """Record the item's publication time; the model has no field for it."""
        published = _parse_published(raw_date)
        if published is not None:
            logger.debug(
                "%s: %r published %s", cls.__name__, title, published.isoformat()
            )


# --------------------------------------------------------------------------- sources


class NationNewsParser(RSSParser):
    """The Nation (nationnews.com), WordPress RSS 2.0.

    The site's own ``<link rel="alternate">`` points at the apex domain (``www.`` is slower
    still). The origin is uncached behind Cloudflare and routinely takes 20-30 seconds to
    send its first byte, hence the raised timeout. Links carry ``utm_*`` parameters and
    excerpts end with the WordPress footer; both are removed.
    """

    source_name: ClassVar[str] = "Nation News"
    urls: ClassVar[list[str]] = ["https://nationnews.com/feed/"]
    request_timeout: ClassVar[float | None] = 60.0


class BarbadosTodayParser(RSSParser):
    """Barbados Today (barbadostoday.bb), WordPress RSS 2.0 (Atom also at ``/feed/atom/``).

    Excerpts open with a featured image and close with the WordPress footer; both are
    stripped, leaving the first paragraph of the story.
    """

    source_name: ClassVar[str] = "Barbados Today"
    urls: ClassVar[list[str]] = ["https://barbadostoday.bb/feed/"]


class BBCBarbadosParser(RSSParser):
    """BBC News topic feed for Barbados, RSS 2.0.

    Items link to ``bbc.co.uk`` with ``at_medium``/``at_campaign`` analytics parameters,
    which are removed. Descriptions are one-sentence plain-text summaries.
    """

    source_name: ClassVar[str] = "BBC News"
    urls: ClassVar[list[str]] = [
        "https://feeds.bbci.co.uk/news/topics/cp7r8vgl2jxt/rss.xml"
    ]


class LoopNewsParser(RSSParser):
    """Loop News Barbados, WordPress RSS 2.0 — DORMANT.

    Digicel closed Loop News in July 2025. ``barbados.loopnews.com`` now returns 404 and the
    relaunched ``www.loopnews.com`` serves an empty feed behind a TLS certificate that
    expired in February 2026. The class is kept, with the last known feed URL, so the source
    can be re-registered in ``app.services.scrape.PARSERS`` if it returns.
    """

    source_name: ClassVar[str] = "Loop News"
    urls: ClassVar[list[str]] = ["https://www.loopnews.com/news/barbados/feed/"]


class BarbadosAdvocateParser(RSSParser):
    """The Barbados Advocate, Drupal RSS 2.0 at ``/rss.xml`` — DORMANT.

    The newspaper ceased publication in 2023 and ``barbadosadvocate.com`` now redirects to
    an unrelated site with a mismatched certificate. The feed escaped its HTML rather than
    using CDATA and its teasers held only an image, so snippets from it are usually empty.
    Kept with the last known feed URL in case the title is revived.
    """

    source_name: ClassVar[str] = "Barbados Advocate"
    urls: ClassVar[list[str]] = ["https://www.barbadosadvocate.com/rss.xml"]
