from datetime import UTC, datetime
import os
from pathlib import Path
import urllib.request

import psycopg

from src.database_config import DATABASE_URL


WEBSITE_OUTPUT_DIR = Path(os.getenv("WEBSITE_OUTPUT_DIR", "./websites"))


def clone_website_to_file(website_id: int, main_url: str, cookie: str | None = None) -> str:
    headers = {"User-Agent": "siteflow-worker/0.1"}
    if cookie is not None:
        headers["Cookie"] = cookie

    request = urllib.request.Request(main_url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read()

    WEBSITE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = WEBSITE_OUTPUT_DIR / str(website_id)
    output_path.write_bytes(content)

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE websites SET last_access_time = %s WHERE id = %s",
            (datetime.now(UTC), website_id),
        )
        connection.commit()

    return str(output_path)
