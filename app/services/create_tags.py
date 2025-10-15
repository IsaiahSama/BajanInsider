from google import genai

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client()

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
