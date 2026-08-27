import asyncio

import procrastinate

from vitaweby.database_config import DATABASE_URL
from vitaweby.tasks import clone_website_to_file


app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=DATABASE_URL)
)


@app.task(name="clone_website", queue="clone")
async def clone_website(website_id: int, main_url: str, cookie: str | None = None) -> str:
    return await asyncio.to_thread(
        clone_website_to_file,
        website_id=website_id,
        main_url=main_url,
        cookie=cookie,
    )
