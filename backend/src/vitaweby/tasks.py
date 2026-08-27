from datetime import UTC, datetime
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import psycopg

from vitaweby.database_config import DATABASE_URL
from vitaweby.storage import get_website_storage


def clone_website_to_file(website_id: int, main_url: str, cookie: str | None = None) -> str:
    storage = get_website_storage()
    with tempfile.TemporaryDirectory(prefix="siteflow-clone-") as temporary_dir:
        mirror_root = Path(temporary_dir) / "frontend"
        output_path = mirror_root / "index.html"
        environment = os.environ.copy()
        environment.pop("SITEFLOW_SCRAPER_COOKIE", None)
        if cookie:
            environment["SITEFLOW_SCRAPER_COOKIE"] = cookie

        subprocess.run(
            [
                sys.executable,
                "-m",
                "vitaweby.scraper",
                main_url,
                str(output_path),
            ],
            env=environment,
            check=True,
        )

        output_uri = ""
        for path in sorted(mirror_root.rglob("*")):
            if not path.is_file():
                continue
            relative_path = path.relative_to(mirror_root).as_posix()
            content_type, _ = mimetypes.guess_type(path)
            saved_uri = storage.save_file(
                website_id=website_id,
                filename=f"frontend/{relative_path}",
                content=path.read_bytes(),
                content_type=content_type or "application/octet-stream",
            )
            if relative_path == "index.html":
                output_uri = saved_uri

        if not output_uri:
            raise RuntimeError("Scraper completed without producing frontend/index.html")

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "UPDATE websites SET last_access_time = %s WHERE id = %s",
            (datetime.now(UTC), website_id),
        )
        connection.commit()

    return output_uri
