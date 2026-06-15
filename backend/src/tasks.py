from datetime import UTC, datetime
import mimetypes
import urllib.request

import psycopg

from src.database_config import DATABASE_URL
from src.storage import get_website_storage


def _content_type_from_response(response: urllib.response.addinfourl) -> str:
    content_type = response.headers.get_content_type()
    if content_type:
        return content_type

    guessed_type, _ = mimetypes.guess_type(response.url)
    return guessed_type or "application/octet-stream"


def _output_filename(content_type: str) -> str:
    if content_type == "text/html":
        return "index.html"

    extension = mimetypes.guess_extension(content_type) or ".bin"
    return f"source{extension}"


def clone_website_to_file(website_id: int, main_url: str, cookie: str | None = None) -> str:
    headers = {"User-Agent": "siteflow-worker/0.1"}
    if cookie is not None:
        headers["Cookie"] = cookie

    request = urllib.request.Request(main_url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read()
        content_type = _content_type_from_response(response)

    output_uri = get_website_storage().save_file(
        website_id=website_id,
        filename=_output_filename(content_type),
        content=content,
        content_type=content_type,
    )

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE websites SET last_access_time = %s WHERE id = %s",
            (datetime.now(UTC), website_id),
        )
        connection.commit()

    return output_uri
