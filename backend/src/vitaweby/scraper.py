from pathlib import Path

import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings


class _PageDownloadSpider(scrapy.Spider):
    name = "page_download"

    def __init__(self, url: str, output_path: Path, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.start_urls = [url]
        self.output_path = output_path

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, meta={"playwright": True})

    def parse(self, response: scrapy.http.Response):
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_bytes(response.body)


def scrape_and_download_website(url: str, output_path: str) -> str:
    """Render `url` with Playwright via Scrapy and save the resulting HTML to `output_path`."""
    settings = get_project_settings()
    settings.set("DOWNLOAD_HANDLERS", {
        "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    })
    settings.set("TWISTED_REACTOR", "twisted.internet.asyncioreactor.AsyncioSelectorReactor")

    process = CrawlerProcess(settings)
    process.crawl(_PageDownloadSpider, url=url, output_path=Path(output_path))
    process.start()

    return output_path
