from google import genai
from app.db.mongo_client import client as db_client

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

async def summarize_latest_news(limit: int = 10) -> str:
    """Summarizes the latest news articles using Gemini API."""

    latest_articles = await db_client.get_entries(0, limit)
    if not latest_articles or not latest_articles.entries:
        return "No articles available to summarize."

    articles = "\n\n".join(f"Title: {article.title}\n Content: {article.content}" for article in latest_articles.entries)

    prompt = f"Summarize the following news articles in a few sentences:\n\n{articles}\n\nSummary:"
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    
    return response.text or "No summary available at this time."