from datetime import datetime

from pydantic import AnyUrl, BaseModel, ConfigDict


class CloneJobCreate(BaseModel):
    url: AnyUrl


class Website(BaseModel):
    website_id: int
    website_name: str
    start_time: datetime
    last_access_time: datetime
    user_id: int | None


class CloneJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: int
    main_url: str
    status: str
    created_at: datetime
    website: Website
    downloaded_items: int = 0
    remaining_items: int = 0
