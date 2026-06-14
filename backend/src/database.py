import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


DATABASE_URL = os.environ["DATABASE_URL"]


def _is_postgres(database_url: str | None = None) -> bool:
    database_url = database_url or DATABASE_URL
    return database_url.startswith(("postgresql://", "postgres://"))


def get_connection() -> Any:
    if _is_postgres():
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)

    raise ValueError("DATABASE_URL must start with postgresql:// or postgres://")


def execute(connection: Any, query: str, params: tuple[Any, ...]):
    return connection.execute(query, params)


def init_db() -> None:
    with get_connection() as connection:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS clone_jobs (
                id BIGSERIAL PRIMARY KEY,
                handle TEXT NOT NULL UNIQUE,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS clone_job_cookies (
                id BIGSERIAL PRIMARY KEY,
                clone_job_id BIGINT NOT NULL
                    REFERENCES clone_jobs (id)
                    ON DELETE CASCADE,
                cookie TEXT,
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_clone_jobs_handle ON clone_jobs (handle)",
            """
            CREATE INDEX IF NOT EXISTS idx_clone_job_cookies_clone_job_id
                ON clone_job_cookies (clone_job_id)
            """,
        )
        for statement in statements:
            connection.execute(statement)
        connection.commit()


def create_clone_job(url: str, cookie: str | None) -> dict[str, Any]:
    handle = uuid4().hex
    created_at = datetime.now(UTC)

    with get_connection() as connection:
        cursor = execute(
            connection,
            """
            INSERT INTO clone_jobs (handle, url, status, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (handle, url, "queued", created_at),
        )
        clone_job_id = cursor.fetchone()["id"]

        execute(
            connection,
            "INSERT INTO clone_job_cookies (clone_job_id, cookie, created_at) VALUES (%s, %s, %s)",
            (clone_job_id, cookie, created_at),
        )
        connection.commit()

    return {
        "handle": handle,
        "url": url,
        "status": "queued",
        "created_at": created_at,
    }


def get_clone_job(handle: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = execute(
            connection,
            """
            SELECT handle, url, status, created_at
            FROM clone_jobs
            WHERE handle = %s
            """,
            (handle,),
        ).fetchone()

    if row is None:
        return None

    return dict(row)


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_URL}")
