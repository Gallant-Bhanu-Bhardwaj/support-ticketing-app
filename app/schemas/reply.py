from pydantic import BaseModel, Field


class ReplyCreate(BaseModel):
    body: str = Field(min_length=1)
    is_internal: bool = False
