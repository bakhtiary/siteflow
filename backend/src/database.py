from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

from src.database_config import DATABASE_URL
from src.queue import clone_website


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
            CREATE TABLE IF NOT EXISTS websites (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                start_time TIMESTAMPTZ NOT NULL,
                last_access_time TIMESTAMPTZ NOT NULL,
                user_id BIGINT
            )
            """,
            """
            ALTER TABLE websites
            ADD COLUMN IF NOT EXISTS last_access_time TIMESTAMPTZ
            """,
            """
            UPDATE websites
            SET last_access_time = start_time
            WHERE last_access_time IS NULL
            """,
            """
            ALTER TABLE websites
            ALTER COLUMN last_access_time SET NOT NULL
            """,
            "DROP TABLE IF EXISTS clone_job_cookies",
            "DROP TABLE IF EXISTS clone_jobs",
        )
        for statement in statements:
            connection.execute(statement)
        connection.commit()


def _website_name_from_url(url: str) -> str:
    parsed_url = urlparse(url)
    return parsed_url.netloc or parsed_url.path or url


def create_clone_job(url: str, cookie: str | None) -> dict[str, Any]:
    created_at = datetime.now(UTC)
    website_name = _website_name_from_url(url)

    with get_connection() as connection:
        website_cursor = execute(
            connection,
            """
            INSERT INTO websites (name, start_time, last_access_time, user_id)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (website_name, created_at, created_at, None),
        )
        website_id = website_cursor.fetchone()["id"]

        job_id = clone_website.configure(connection=connection).defer(
            website_id=website_id,
            main_url=url,
            cookie=cookie,
        )
        connection.commit()

    return {
        "job_id": job_id,
        "main_url": url,
        "status": "todo",
        "created_at": created_at,
        "website": {
            "website_id": website_id,
            "website_name": website_name,
            "start_time": created_at,
            "last_access_time": created_at,
            "user_id": None,
        },
    }


def get_clone_job(job_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = execute(
            connection,
            """
            SELECT
                procrastinate_jobs.id AS job_id,
                procrastinate_jobs.args->>'main_url' AS main_url,
                procrastinate_jobs.status,
                COALESCE(procrastinate_events.at, websites.start_time) AS created_at,
                websites.id AS website_id,
                websites.name AS website_name,
                websites.start_time,
                websites.last_access_time,
                websites.user_id
            FROM procrastinate_jobs
            JOIN websites
                ON websites.id = (procrastinate_jobs.args->>'website_id')::BIGINT
            LEFT JOIN procrastinate_events
                ON procrastinate_events.job_id = procrastinate_jobs.id
                AND procrastinate_events.type = 'deferred'
            WHERE procrastinate_jobs.id = %s
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "job_id": row["job_id"],
        "main_url": row["main_url"],
        "status": row["status"],
        "created_at": row["created_at"],
        "website": {
            "website_id": row["website_id"],
            "website_name": row["website_name"],
            "start_time": row["start_time"],
            "last_access_time": row["last_access_time"],
            "user_id": row["user_id"],
        },
    }


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_URL}")
