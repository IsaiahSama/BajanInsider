from typing import Annotated
from datetime import datetime
from pydantic import BaseModel, BeforeValidator, Field

PyObjectId = Annotated[str, BeforeValidator(str)]


class NewsEntry(BaseModel):
    """
    Model representing a news entry.
    """

    id: PyObjectId | None = Field(alias="_id", default=None)
    title: str
    content: str
    source: str
    link: str
    tags: str = "" # Comma separated tags (tag1,tag2,tag3)
    date_scraped: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name: bool = True
        arbitrary_types_allowed: bool = True
