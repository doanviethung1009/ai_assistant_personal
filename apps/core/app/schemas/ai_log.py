from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AiLogCategory


class AiLogBase(BaseModel):
    category: AiLogCategory = Field(default=AiLogCategory.OTHER)
    prompt: str = Field(min_length=1)
    handling: str = Field(min_length=1)
    response: str = Field(min_length=1)


class AiLogCreate(AiLogBase):
    pass


class AiLogUpdate(BaseModel):
    category: AiLogCategory | None = None
    prompt: str | None = None
    handling: str | None = None
    response: str | None = None


class AiLogRead(AiLogBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
