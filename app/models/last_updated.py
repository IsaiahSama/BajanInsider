from uuid import UUID, uuid4
from pydantic import Field, BaseModel


class LastUpdated(BaseModel):
    """
    Field to know when the Database was last updated
    """

    id: UUID = Field(alias="_id", default=uuid4())
    last_updated: str = Field(...)
