from contextlib import asynccontextmanager
from datetime import UTC, datetime
import os
from pathlib import Path
import sqlite3
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import AnyUrl, BaseModel, ConfigDict


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./siteflow.db")


def _database_path(database_url: str | None = None) -> Path:
    database_url = database_url or DATABASE_URL
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// DATABASE_URL values are supported")

    path = Path(database_url.removeprefix("sqlite:///"))
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def get_connection() -> sqlite3.Connection:
    db_path = _database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS clone_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handle TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clone_job_cookies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clone_job_id INTEGER NOT NULL,
                cookie TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (clone_job_id)
                    REFERENCES clone_jobs (id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_clone_jobs_handle
                ON clone_jobs (handle);
            CREATE INDEX IF NOT EXISTS idx_clone_job_cookies_clone_job_id
                ON clone_job_cookies (clone_job_id);
            """
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


class CloneJobCreate(BaseModel):
    url: AnyUrl


class CloneJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    handle: str
    url: str
    status: str
    created_at: datetime


def db_connection():
    with get_connection() as connection:
        yield connection


@app.post(
    "/clone",
    response_model=CloneJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_clone_job(
    payload: CloneJobCreate,
    response: Response,
    connection: Annotated[sqlite3.Connection, Depends(db_connection)],
    cookie: Annotated[str | None, Header(alias="Cookie")] = None,
) -> CloneJobResponse:
    handle = uuid4().hex
    created_at = datetime.now(UTC).isoformat()

    cursor = connection.execute(
        """
        INSERT INTO clone_jobs (handle, url, status, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (handle, str(payload.url), "queued", created_at),
    )
    connection.execute(
        """
        INSERT INTO clone_job_cookies (clone_job_id, cookie, created_at)
        VALUES (?, ?, ?)
        """,
        (cursor.lastrowid, cookie, created_at),
    )
    connection.commit()

    response.headers["Location"] = f"/clone/{handle}"
    return CloneJobResponse(
        handle=handle,
        url=str(payload.url),
        status="queued",
        created_at=datetime.fromisoformat(created_at),
    )


@app.get("/clone/{handle}", response_model=CloneJobResponse)
def get_clone_job(
    handle: str,
    connection: Annotated[sqlite3.Connection, Depends(db_connection)],
) -> CloneJobResponse:
    row = connection.execute(
        """
        SELECT handle, url, status, created_at
        FROM clone_jobs
        WHERE handle = ?
        """,
        (handle,),
    ).fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clone job not found")

    return CloneJobResponse(
        handle=row["handle"],
        url=row["url"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {_database_path()}")
