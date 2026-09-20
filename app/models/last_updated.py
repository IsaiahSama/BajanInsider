from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field

PyObjectId = Annotated[str, BeforeValidator(str)]


def today() -> str:
    """Returns the current local date formatted as `%Y-%m-%d`."""
    return datetime.now().astimezone().strftime("%Y-%m-%d")


class LastUpdated(BaseModel):
    """
    Field to know when the Database was last updated
    """

    id: PyObjectId | None = Field(alias="_id", default=None)
    last_updated: str = Field(default_factory=today)
