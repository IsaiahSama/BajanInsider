from hashlib import sha256

from google import genai

from app.db.mongo_client import client as db_client
from app.models import NewsEntry
from app.services.logger import get_logger

logger = get_logger(__name__)

CONTEXT = (
    "You are an amazing assistant that specializes in summarizing news articles. "
    "You are engaging, use easy to understand language and the occasional joke, "
    "and always sound informed, so your summaries are easily digestible for older "
    "folks as well. However, you always, ALWAYS, only use the information you are "
    "given when giving your summaries.\n\n"
    "Format every summary as one short opening sentence, followed by 3 to 6 bullet "
    "points. Put each bullet point on its own line starting with \"- \", and keep "
    "each one to one or two sentences about a single story or group of related "
    "stories. Use plain text only: no headings, bold, or other markdown."
)

# Line prefixes split_summary treats as bullet points. Gemini is asked for "- "
# but sometimes falls back to the other two.
BULLET_MARKERS = ("- ", "* ", "• ")

MODEL = "gemini-2.5-flash"

# Created on first use so that importing the app does not require GEMINI_API_KEY.
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Returns the shared Gemini client, creating it on first use.

    The client reads its API key from the `GEMINI_API_KEY` environment variable.

    Returns:
        genai.Client: The cached Gemini client.
    """
    global _client

    if _client is None:
        _client = genai.Client()

    return _client


async def summarize_latest_news(limit: int = 10) -> str:
    """Summarizes the latest news articles using Gemini API.

    Summaries are cached by a hash of the article titles. Only one request at
    a time may generate a new summary; concurrent callers get a loading message.

    Args:
        limit (int): How many of the newest articles to summarize.

    Returns:
        str: The summary, or a user-facing status message.
    """

    latest_articles = await db_client.get_entries(0, limit)

    if not latest_articles or not latest_articles.entries:
        return "No articles available to summarize."

    titles = " ".join(article.title for article in latest_articles.entries)
    # The prompt is part of the key so that editing it regenerates the summary
    # instead of serving one cached in the old format.
    title_hash = sha256(f"{CONTEXT}\n{titles}".encode("utf-8")).hexdigest()

    cached_summary = await db_client.get_summary(title_hash)
    if cached_summary:
        return cached_summary.ai_summary

    # Only the caller that acquires the lock talks to Gemini.
    if not await db_client.test_and_set():
        logger.info("Summary lock not acquired; another request is generating it")
        return "Summary is loading... Refresh in a few seconds!"

    logger.info("Summary lock acquired; generating summary")

    try:
        return await _generate_summary(title_hash, latest_articles.entries)
    finally:
        # Always release, even if generation or caching raised, so a failed
        # request cannot leave the lock held for everyone else.
        await db_client.release_lock()
        logger.info("Summary lock released")


async def _generate_summary(title_hash: str, articles: list[NewsEntry]) -> str:
    """Asks Gemini to summarize `articles` and caches the result under `title_hash`.

    Args:
        title_hash (str): Cache key derived from the article titles.
        articles (list[NewsEntry]): The articles to summarize.

    Returns:
        str: The generated summary, or a user-facing fallback message.
    """

    articles_text = "\n\n".join(
        f"Title: {article.title}\n Content: {article.content}" for article in articles
    )
    prompt = f"{CONTEXT}\n\nSummarize the following news articles:\n\n{articles_text}\n\nSummary:"

    try:
        # The async client keeps the event loop free while Gemini responds; the
        # sync `client.models` surface would stall every other request.
        response = await get_client().aio.models.generate_content(
            model=MODEL, contents=prompt
        )
    except Exception:
        logger.exception("Gemini summary generation failed")
        return "Could not generate summary at this time."

    if response.text:
        await db_client.add_summary(title_hash, response.text)

    return response.text or "No summary available at this time."


def split_summary(text: str) -> list[str | list[str]]:
    """Splits a summary into paragraphs and bullet lists for display.

    Consecutive bullet lines become one list and every other non-blank line is
    a paragraph. Text without bullets, such as summaries cached before the
    bullet prompt or the status messages, comes back as plain paragraphs.

    Args:
        text (str): The summary or status message to display.

    Returns:
        list[str | list[str]]: Paragraphs and lists of bullet points, in order.
    """

    blocks: list[str | list[str]] = []

    for raw_line in text.splitlines():
        # Bold markers are dropped rather than rendered; the prompt forbids them.
        line = raw_line.strip().replace("**", "")
        if not line:
            continue

        if not line.startswith(BULLET_MARKERS):
            blocks.append(line)
            continue

        point = line[2:].strip()
        if blocks and isinstance(blocks[-1], list):
            blocks[-1].append(point)
        else:
            blocks.append([point])

    return blocks
