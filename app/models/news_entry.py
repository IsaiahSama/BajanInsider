from typing import Annotated

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
    date_scraped: str
    tags: str = "" # Comma separated tags (tag1,tag2,tag3)

    class Config:
        populate_by_name: bool = True
        arbitrary_types_allowed: bool = True
