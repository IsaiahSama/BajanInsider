from google import genai
from app.db.mongo_client import client as db_client

from hashlib import sha256

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

SUMMARIZE_CONTEXT = "You are an amazing assistant that specializes in summarizing news articles. You are engaging, detailed, and capable of making mini stories with whatever information you have. When presenting, you use easy to understand language, occassional jokes, and always sound informed. However, you always, ALWAYS, only use the information you are given when giving your summaries. Ensure your summaries are no more than 10 sentences, and are easily digestible for older folks as well."

async def summarize_latest_news(limit: int = 10) -> str:
    """Summarizes the latest news articles using Gemini API."""

    latest_articles = await db_client.get_entries(0, limit)
    
    if not latest_articles or not latest_articles.entries:
        return "No articles available to summarize."
    
    titles = " ".join(article.title for article in latest_articles.entries)
    title_hash = sha256(titles.encode('utf-8')).hexdigest()
    
    cached_summary = await db_client.get_summary(title_hash)
    if cached_summary:
        return cached_summary.ai_summary

    articles = "\n\n".join(f"Title: {article.title}\n Content: {article.content}" for article in latest_articles.entries)

    prompt = f"{SUMMARIZE_CONTEXT}\n\nSummarize the following news articles in a few sentences:\n\n{articles}\n\nSummary:"
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
    except Exception as e:
        print(e)
        return "Could not generate summary at this time."
    
    if response.text:
        await db_client.add_summary(title_hash, response.text)
        
    return response.text or "No summary available at this time."

TAG_CONTEXT = "You are an expert at generating concise and relevant tags for news articles. You understand the main topics and themes of the content provided and can distill them into three (3) key tags that accurately represent the essence of the article. When responding, respond with the tags in a comma separated format as follows:\nTAGS: tag1,tag2,tag3\n"

async def create_tags(title:str, content:str) -> str:
    """Generates tags for the given content using Gemini API."""

    prompt = f"{TAG_CONTEXT}\n\nContent: {title}\n{content}\n\nTags:"
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
    except Exception as e:
        print(e)
        return ""
    
    if response.text:
        tags = response.text.split("TAGS:")[-1].strip()
        return tags
    
    return ""