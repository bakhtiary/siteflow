import time

import psycopg
import procrastinate

from src.database_config import DATABASE_URL
from src.tasks import clone_website_to_file


app = procrastinate.App(
    connector=procrastinate.SyncPsycopgConnector(conninfo=DATABASE_URL)
)


def _wait_for_postgres(*, retries: int = 10, delay_seconds: float = 1.0) -> None:
    for attempt in range(1, retries + 1):
        try:
            with psycopg.connect(DATABASE_URL):
                return
        except psycopg.OperationalError:
            if attempt == retries:
                raise
            time.sleep(delay_seconds)


def open_queue() -> None:
    _wait_for_postgres()
    ensure_queue_schema()
    app.open()


def ensure_queue_schema() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute("SELECT pg_advisory_lock(hashtext('siteflow_procrastinate_schema'))")
        try:
            should_apply_schema = not _queue_schema_exists()
            if not should_apply_schema:
                return

            app.open()
            try:
                app.schema_manager.apply_schema()
            finally:
                app.close()
        finally:
            connection.execute(
                "SELECT pg_advisory_unlock(hashtext('siteflow_procrastinate_schema'))"
            )
            connection.commit()


def _queue_schema_exists() -> bool:
    with psycopg.connect(DATABASE_URL) as connection:
        exists = connection.execute(
            "SELECT to_regclass('public.procrastinate_jobs') IS NOT NULL"
        ).fetchone()
    return bool(exists[0])


@app.task(name="clone_website", queue="clone")
def clone_website(website_id: int, main_url: str, cookie: str | None = None) -> str:
    return clone_website_to_file(website_id=website_id, main_url=main_url, cookie=cookie)
