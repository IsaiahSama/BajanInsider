from typing import Annotated
from pydantic import BeforeValidator, Field, BaseModel


PyObjectId = Annotated[str, BeforeValidator(str)]


class LastUpdated(BaseModel):
    """
    Field to know when the Database was last updated
    """

    id: PyObjectId | None = Field(alias="_id", default=None)
    last_updated: str = Field(...)
