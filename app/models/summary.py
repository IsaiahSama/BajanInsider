from pydantic import BaseModel

class Summary(BaseModel):
    """
    Model representing the AI summary of last n news entries.
    
    Attributes:
        title_hash (str): A hash of the titles of the summarized articles to be used for caching.
        ai_summary (str): The generated summary text.
    """

    title_hash: str
    ai_summary: str