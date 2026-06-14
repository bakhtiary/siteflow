from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response, status

from src.database import create_clone_job as create_clone_job_record
from src.database import get_clone_job as get_clone_job_record
from src.database import init_db
from src.model import CloneJobCreate, CloneJobResponse
from src.queue import app as queue_app
from src.queue import open_queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_queue()
    init_db()
    try:
        yield
    finally:
        queue_app.close()


app = FastAPI(lifespan=lifespan)


@app.post(
    "/clone",
    response_model=CloneJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_clone_job(
    payload: CloneJobCreate,
    response: Response,
    cookie: Annotated[str | None, Header(alias="Cookie")] = None,
) -> CloneJobResponse:
    clone_job = create_clone_job_record(str(payload.url), cookie)
    response.headers["Location"] = f"/clone/{clone_job['job_id']}"
    return CloneJobResponse(**clone_job)


@app.get("/clone/{job_id}", response_model=CloneJobResponse)
def get_clone_job(job_id: int) -> CloneJobResponse:
    clone_job = get_clone_job_record(job_id)

    if clone_job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clone job not found")

    return CloneJobResponse(
        job_id=clone_job["job_id"],
        main_url=clone_job["main_url"],
        status=clone_job["status"],
        created_at=clone_job["created_at"]
        if isinstance(clone_job["created_at"], datetime)
        else datetime.fromisoformat(clone_job["created_at"]),
        website=clone_job["website"],
    )
