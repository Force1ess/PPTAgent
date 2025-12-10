import asyncio
import tempfile
from pathlib import Path
from typing import Literal

from fake_useragent import UserAgent
from pdf2image import convert_from_path
from playwright.async_api import async_playwright
from pypdf import PdfWriter

from deeppresenter.utils.constants import PDF_OPTIONS
from deeppresenter.utils.log import error, info

FAKE_UA = UserAgent()

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-blink-features=AutomationControlled",
]

ANTI_DETECTION = """
() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
    delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    if (!window.chrome) { window.chrome = { runtime: {} }; }
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
}
"""

ASPECT_RATIOS = {
    "widescreen": {"width": "338.67mm", "height": "190.5mm"},  # 16:9
    "normal": {"width": "254mm", "height": "190.5mm"},  # 4:3
    "A1": {"width": "594mm", "height": "841mm"},  # A1
}


class PlaywrightConverter:
    _playwright = None
    _browser = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.context = None
        self.page = None

    async def __aenter__(self):
        """Async context manager entry"""
        async with PlaywrightConverter._lock:
            if PlaywrightConverter._browser is None:
                PlaywrightConverter._playwright = await async_playwright().start()
                PlaywrightConverter._browser = (
                    await PlaywrightConverter._playwright.chromium.launch(
                        headless=True, args=LAUNCH_ARGS
                    )
                )

        self.context = await PlaywrightConverter._browser.new_context(
            user_agent=FAKE_UA.random,
            bypass_csp=True,
        )
        await self.context.add_init_script(ANTI_DETECTION)
        self.page = await self.context.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit, only close context"""
        if self.context:
            await self.context.close()

    async def convert_to_pdf(
        self,
        html_files: list[str],
        output_pdf: Path,
        aspect_ratio: Literal["widescreen", "normal", "A1"],
    ):
        if isinstance(output_pdf, str):
            output_pdf = Path(output_pdf)
        pdf_files = [tempfile.mkstemp(suffix=".pdf")[1] for _ in range(len(html_files))]
        folder = output_pdf.parent / f".slide_images-pdf-{output_pdf.stem}"
        folder.mkdir(exist_ok=True, parents=True)

        page = await self.context.new_page()
        try:
            for html, pdf in zip(sorted(html_files), pdf_files):
                await page.goto(Path(html).resolve().as_uri(), wait_until="networkidle")
                await page.pdf(path=pdf, **PDF_OPTIONS, **ASPECT_RATIOS[aspect_ratio])
        except Exception as e:
            error(f"Failed to convert HTML to PDF: {e}")
            raise e
        finally:
            await page.close()

        with PdfWriter() as merger:
            for pdf_file in pdf_files:
                merger.append(pdf_file)

            with open(output_pdf, "wb") as f:
                merger.write(f)

        for idx, page in enumerate(convert_from_path(output_pdf, dpi=100)):
            page.save(folder / f"slide_{(idx + 1):02d}.jpg")
        info(f"Converted PDF saved at: {output_pdf}")
        return folder


if __name__ == "__main__":
    from glob import glob

    async def main():
        async with PlaywrightConverter() as converter:
            htmls = glob("/opt/workspace/935b4e54/slides/*.html")
            output_pdf = Path("output.pdf")
            await converter.convert_to_pdf(htmls, output_pdf, "widescreen")

    asyncio.run(main())
