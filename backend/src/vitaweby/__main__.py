import asyncio
from contextlib import asynccontextmanager
from contextlib import suppress
from datetime import datetime
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response, status
from fastapi.responses import RedirectResponse

from vitaweby.database import create_clone_job as create_clone_job_record
from vitaweby.database import get_clone_job as get_clone_job_record
from vitaweby.database import init_db
from vitaweby.model import CloneJobCreate, CloneJobResponse
from vitaweby.vita_queue import app as queue_app
from vitaweby.vita_queue import open_queue
from vitaweby.storage import get_website_storage
from vitaweby.worker_queue import app as worker_app


async def run_worker() -> None:
    async with worker_app.open_async():
        await worker_app.run_worker_async(
            queues=["clone"],
            install_signal_handlers=False,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_queue()
    init_db()
    worker_task = asyncio.create_task(run_worker(), name="siteflow-worker")
    try:
        yield
    finally:
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task
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


@app.get("/view/{website_id}", include_in_schema=False)
def redirect_to_website_root(website_id: int) -> RedirectResponse:
    return RedirectResponse(url=f"{website_id}/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/view/{website_id}/")
@app.get("/view/{website_id}/{file_path:path}")
def view_website(website_id: int, file_path: str = "") -> Response:
    requested_path = file_path

    if not requested_path or requested_path.endswith("/"):
        requested_path = f"{requested_path}index.html"

    try:
        stored_file = get_website_storage().read_file(website_id, f"frontend/{requested_path}")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website output not found")

    if stored_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Website output not found")

    return Response(content=stored_file.content, media_type=stored_file.content_type)

@app.get("/")
def health():
    return {"status": "ok"}
