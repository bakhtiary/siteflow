from dataclasses import dataclass
import mimetypes
import os
from pathlib import Path, PurePosixPath
from typing import Protocol


@dataclass(frozen=True)
class StoredFile:
    content: bytes
    content_type: str


class WebsiteStorage(Protocol):
    def save_file(
        self,
        website_id: int,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        ...

    def read_file(self, website_id: int, filename: str) -> StoredFile | None:
        ...


class LocalWebsiteStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save_file(
        self,
        website_id: int,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        output_dir = self.root / str(website_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._site_path(website_id, filename)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)
        return str(output_path)

    def read_file(self, website_id: int, filename: str) -> StoredFile | None:
        path = self._site_path(website_id, filename)

        if not path.is_file():
            return None

        content_type, _ = mimetypes.guess_type(path)
        return StoredFile(
            content=path.read_bytes(),
            content_type=content_type or "application/octet-stream",
        )

    def _site_path(self, website_id: int, filename: str) -> Path:
        site_root = (self.root / str(website_id)).resolve()
        path = (site_root / _safe_storage_path(filename)).resolve()

        if path != site_root and site_root not in path.parents:
            raise ValueError("Storage path escapes website directory")

        return path


class GcsWebsiteStorage:
    def __init__(self, bucket_name: str) -> None:
        try:
            from google.cloud import storage
        except ImportError as error:
            raise RuntimeError(
                "GCS storage requires the google-cloud-storage package to be installed"
            ) from error

        self.bucket = storage.Client().bucket(bucket_name)

    def _object_name(self, website_id: int, filename: str) -> str:
        return f"{website_id}/{_safe_storage_path(filename).as_posix()}"

    def save_file(
        self,
        website_id: int,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        object_name = self._object_name(website_id, filename)
        blob = self.bucket.blob(object_name)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{self.bucket.name}/{object_name}"

    def read_file(self, website_id: int, filename: str) -> StoredFile | None:
        blob = self.bucket.blob(self._object_name(website_id, filename))

        if not blob.exists():
            return None

        return StoredFile(
            content=blob.download_as_bytes(),
            content_type=blob.content_type or "application/octet-stream",
        )


def get_website_storage() -> WebsiteStorage:
    backend = os.getenv("WEBSITE_STORAGE_BACKEND", "local").lower()

    if backend == "local":
        root = Path(os.getenv("WEBSITE_OUTPUT_DIR", "./websites"))
        return LocalWebsiteStorage(root)

    if backend == "gcs":
        bucket_name = os.getenv("WEBSITE_STORAGE_BUCKET")
        if not bucket_name:
            raise RuntimeError("WEBSITE_STORAGE_BUCKET is required when WEBSITE_STORAGE_BACKEND=gcs")
        return GcsWebsiteStorage(bucket_name)

    raise RuntimeError(f"Unsupported WEBSITE_STORAGE_BACKEND: {backend}")


def _safe_storage_path(filename: str) -> Path:
    path = PurePosixPath(filename)

    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Storage path must be relative to the website directory")

    return Path(*path.parts)
