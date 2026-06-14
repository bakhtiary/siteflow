from datetime import datetime

from pydantic import AnyUrl, BaseModel, ConfigDict


class CloneJobCreate(BaseModel):
    url: AnyUrl


class CloneJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    handle: str
    url: str
    status: str
    created_at: datetime
