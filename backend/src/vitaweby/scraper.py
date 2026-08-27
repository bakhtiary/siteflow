import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urldefrag, urljoin, urlsplit

import scrapy
from lxml import html
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


_ASSET_ATTRIBUTES = {
    "audio": ("src",), "embed": ("src",), "iframe": ("src",),
    "img": ("src", "srcset"), "input": ("src",), "link": ("href",),
    "object": ("data",), "script": ("src",), "source": ("src", "srcset"),
    "track": ("src",), "video": ("src", "poster"),
}
_CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_CSS_IMPORT_RE = re.compile(r"(@import\s+)(?!url\()(['\"])(.*?)\2", re.IGNORECASE)
_SKIPPED_SCHEMES = ("data:", "javascript:", "mailto:", "tel:", "blob:", "#")


def _clean_url(value: str, base_url: str) -> str | None:
    value = value.strip()
    if not value or value.lower().startswith(_SKIPPED_SCHEMES):
        return None
    absolute, _ = urldefrag(urljoin(base_url, value))
    return absolute if urlsplit(absolute).scheme in {"http", "https"} else None


def _safe_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", value) or "_"


def _url_path(url: str, root_host: str, *, page: bool) -> PurePosixPath:
    parsed = urlsplit(url)
    path = PurePosixPath(*(_safe_part(part) for part in parsed.path.split("/") if part))
    if page:
        if not path.parts or parsed.path.endswith("/"):
            path /= "index.html"
        elif not Path(path.name).suffix:
            path /= "index.html"
    elif not path.parts:
        path = PurePosixPath("index")
    if parsed.query:
        digest = hashlib.sha256(parsed.query.encode()).hexdigest()[:10]
        path = path.with_name(f"{path.stem}__q_{digest}{path.suffix}")
    if parsed.hostname != root_host:
        path = PurePosixPath("_external", _safe_part(parsed.netloc)) / path
    return path


def _relative_reference(source: Path, target: Path) -> str:
    return Path(os.path.relpath(target, source.parent)).as_posix()


def _srcset_urls(value: str) -> list[str]:
    return [item.strip().split()[0] for item in value.split(",") if item.strip()]


class _WebsiteDownloadSpider(scrapy.Spider):
    name = "website_download"

    def __init__(
        self,
        url: str,
        output_path: Path,
        cookie: str | None = None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.start_url = urldefrag(url)[0]
        self.root_host = urlsplit(url).hostname or ""
        self.output_root = output_path.parent
        self.home_path = output_path
        self.linked_pages: dict[str, Path] = {}
        self.request_headers = {"Cookie": cookie} if cookie else {}

    async def start(self):
        yield scrapy.Request(
            self.start_url,
            callback=self.parse_page,
            headers=self.request_headers,
            meta={"playwright": True, "is_home": True},
        )

    def _page_path(self, url: str) -> Path:
        if urldefrag(url)[0] == self.start_url:
            return self.home_path
        return self.output_root / "linked-pages" / _url_path(url, self.root_host, page=True)

    def _asset_path(self, url: str) -> Path:
        return self.output_root / _url_path(url, self.root_host, page=False)

    @staticmethod
    def _write(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def _rewrite_url(self, value: str, base_url: str, source: Path, *, page: bool) -> str:
        absolute = _clean_url(value, base_url)
        if absolute is None:
            return value
        target = self._page_path(absolute) if page else self._asset_path(absolute)
        return _relative_reference(source, target)

    def _is_same_domain(self, url: str) -> bool:
        hostname = (urlsplit(url).hostname or "").removeprefix("www.")
        root_hostname = self.root_host.removeprefix("www.")
        return hostname == root_hostname

    def _write_link_manifest(self) -> None:
        entries = [
            {
                "url": url,
                "file": path.relative_to(self.output_root).as_posix(),
            }
            for url, path in sorted(self.linked_pages.items())
        ]
        manifest = self.output_root / "linked-pages.json"
        self._write(manifest, (json.dumps(entries, indent=2) + "\n").encode())

    def parse_page(self, response: scrapy.http.Response):
        if response.meta.get("is_home"):
            # Treat the landing host as canonical when the supplied URL redirects
            # between common variants such as example.com and www.example.com.
            self.start_url = urldefrag(response.url)[0]
            self.root_host = urlsplit(response.url).hostname or self.root_host
        destination = self._page_path(response.url)
        document = html.fromstring(response.body, base_url=response.url)
        for base in document.xpath("//base"):
            base.getparent().remove(base)

        for element in document.xpath("//*[@href or @src or @srcset or @data or @poster]"):
            tag = element.tag.lower() if isinstance(element.tag, str) else ""
            if tag == "a" and element.get("href"):
                value = element.get("href")
                joined = urljoin(response.url, value)
                absolute, fragment = urldefrag(joined)
                if urlsplit(absolute).scheme in {"http", "https"} and self._is_same_domain(absolute):
                    target = self._page_path(absolute)
                    self.linked_pages.setdefault(absolute, target)
                    local = _relative_reference(destination, target)
                    element.set("href", f"{local}#{fragment}" if fragment else local)
                elif urlsplit(absolute).scheme in {"http", "https"}:
                    element.set("href", joined)
                continue

            for attribute in _ASSET_ATTRIBUTES.get(tag, ()):
                value = element.get(attribute)
                if not value:
                    continue
                for raw_url in _srcset_urls(value) if attribute == "srcset" else [value]:
                    absolute = _clean_url(raw_url, response.url)
                    if absolute:
                        yield scrapy.Request(absolute, callback=self.parse_asset)
                if attribute == "srcset":
                    candidates = []
                    for candidate in value.split(","):
                        pieces = candidate.strip().split(maxsplit=1)
                        if pieces:
                            pieces[0] = self._rewrite_url(pieces[0], response.url, destination, page=False)
                            candidates.append(" ".join(pieces))
                    element.set(attribute, ", ".join(candidates))
                else:
                    element.set(attribute, self._rewrite_url(value, response.url, destination, page=False))
                # Localized stylesheets may be rewritten (for example, CSS url()
                # references), so the origin server's SRI hash is no longer valid.
                element.attrib.pop("integrity", None)

        css_nodes = document.xpath("//style | //*[@style]")
        for node in css_nodes:
            attribute = "style" if node.get("style") is not None else None
            css = node.get(attribute) if attribute else node.text
            if not css:
                continue
            rewritten, assets = self._rewrite_css(css, response.url, destination)
            if attribute:
                node.set(attribute, rewritten)
            else:
                node.text = rewritten
            for asset_url in assets:
                yield scrapy.Request(asset_url, callback=self.parse_asset)

        rendered = html.tostring(document, encoding="utf-8", method="html", doctype="<!DOCTYPE html>")
        self._write(destination, rendered)
        self._write_link_manifest()

    def parse_asset(self, response: scrapy.http.Response):
        destination = self._asset_path(response.url)
        content_type = response.headers.get(b"Content-Type", b"").decode(errors="ignore").lower()
        is_css = "text/css" in content_type or urlsplit(response.url).path.lower().endswith(".css")
        if not is_css:
            self._write(destination, response.body)
            return

        rewritten, discovered = self._rewrite_css(response.text, response.url, destination)
        self._write(destination, rewritten.encode())
        for asset_url in discovered:
            yield scrapy.Request(asset_url, callback=self.parse_asset)

    def _rewrite_css(self, css: str, base_url: str, destination: Path) -> tuple[str, list[str]]:
        discovered = []

        def replace(match: re.Match) -> str:
            absolute = _clean_url(match.group(2), base_url)
            if absolute is None:
                return match.group(0)
            discovered.append(absolute)
            return f"url('{_relative_reference(destination, self._asset_path(absolute))}')"

        rewritten = _CSS_URL_RE.sub(replace, css)

        def replace_import(match: re.Match) -> str:
            absolute = _clean_url(match.group(3), base_url)
            if absolute is None:
                return match.group(0)
            discovered.append(absolute)
            local = _relative_reference(destination, self._asset_path(absolute))
            return f"{match.group(1)}'{local}'"

        return _CSS_IMPORT_RE.sub(replace_import, rewritten), discovered


def scrape_and_download_website(
    url: str,
    output_path: str,
    cookie: str | None = None,
) -> str:
    """Mirror one rendered page and the assets referenced by it."""
    settings = get_project_settings()
    settings.set("DOWNLOAD_HANDLERS", {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    })
    settings.set("TWISTED_REACTOR", "twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    settings.set("ROBOTSTXT_OBEY", True)
    settings.set("LOG_LEVEL", "INFO")

    destination = Path(output_path).resolve()
    process = CrawlerProcess(settings)
    process.crawl(
        _WebsiteDownloadSpider,
        url=url,
        output_path=destination,
        cookie=cookie,
    )
    process.start()
    return str(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mirror one rendered web page")
    parser.add_argument("url")
    parser.add_argument("output_path")
    args = parser.parse_args()
    scrape_and_download_website(
        args.url,
        args.output_path,
        cookie=os.getenv("SITEFLOW_SCRAPER_COOKIE"),
    )


if __name__ == "__main__":
    main()
