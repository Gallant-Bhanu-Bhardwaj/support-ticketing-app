from pydantic import BaseModel


class CollaboratorAdd(BaseModel):
    user_id: int
