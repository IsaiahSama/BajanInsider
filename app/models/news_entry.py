from uuid import UUID, uuid4
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict


class NewsEntry(BaseModel):
    """
    Model representing a news entry.
    """

    id: UUID = Field(alias="_id", default=uuid4())
    title: str = Field(...)
    content: str = Field(...)
    source: str = Field(...)
    link: str = Field(...)
    date_scraped: str = Field(...)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
