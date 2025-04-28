from typing import Annotated
from pydantic import BaseModel, BeforeValidator, Field
from pydantic.config import ConfigDict

PyObjectId = Annotated[str, BeforeValidator(str)]


class NewsEntry(BaseModel):
    """
    Model representing a news entry.
    """

    id: PyObjectId | None = Field(alias="_id", default=None)
    title: str = Field(...)
    content: str = Field(...)
    source: str = Field(...)
    link: str = Field(...)
    date_scraped: str = Field(...)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)
