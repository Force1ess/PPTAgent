import asyncio
import base64
import re
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Literal

import httpx
from appcore import mcp
from fake_useragent import UserAgent
from mcp.types import ImageContent
from mistune import html as markdown_to_html
from PIL import Image
from pptagent.utils import get_html_table_image, ppt_to_images

from deeppresenter.utils.config import RETRY_TIMES
from deeppresenter.utils.webview import convert_html_to_pptx

FAKE_UA = UserAgent()


@mcp.tool()
async def download_file(url: str, output_path: str) -> str:
    """
    Download a file from a URL and save it to a local path.
    """
    # Create directory if it doesn't exist
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    for retry in range(RETRY_TIMES):
        try:
            await asyncio.sleep(retry)
            async with httpx.AsyncClient(
                headers={"User-Agent": FAKE_UA.random},
                follow_redirects=True,
                verify=False,
            ) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    with open(output_path, "wb") as f:
                        async for chunk in response.aiter_bytes(8192):
                            f.write(chunk)
                    break
        except:
            pass
    else:
        return f"Failed to download file from {url}"

    result = f"File downloaded to {output_path}"
    if output_path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
        try:
            with Image.open(output_path) as img:
                width, height = img.size
                result += f" (resolution: {width}x{height})"
        except Exception as e:
            return f"The provided URL does not point to a valid image file: {e}"
    return result


@mcp.tool()
def markdown_table_to_image(markdown_table: str, path: str, css: str) -> str:
    """
    Convert a markdown table to an image and save it to the specified path.

    Args:
        markdown_table (str): The markdown table content to convert
        path (str): The file path where the image will be saved
        css (str): Custom CSS styles for the table. Use class selectors
                            (table, thead, th, td) to style the table elements. Avoid
                            changing background colors outside the table area.

    Returns:
        str: Confirmation message with the path to the saved image
    """
    html = markdown_to_html(markdown_table)
    get_html_table_image(html, path, css)
    return f"Markdown table converted to image and saved to {path}"


@mcp.tool()
async def inspect_slide(
    html_file: str, aspect_ratio: Literal["widescreen", "normal", "A1"] = "widescreen"
) -> ImageContent | str:
    """
    Read the HTML file as an image.
    """
    html_file = Path(html_file).absolute()
    if not (html_file.exists() and html_file.suffix == ".html"):
        return f"HTML path {html_file} does not exist or is not an HTML file"
    if aspect_ratio not in ["widescreen", "normal", "A1"]:
        return "aspect_ratio should be one of 'widescreen', 'normal', 'A1'"
    try:
        pptx_path = convert_html_to_pptx(html_file, aspect_ratio=aspect_ratio)
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            ppt_to_images(str(pptx_path), str(output_dir))
            image_path = output_dir / "slide_0001.jpg"
            if not image_path.exists():
                return "Slide inspection failed: PPTX to image conversion produced no output."
            image_data = image_path.read_bytes()
        return ImageContent(
            type="image",
            data=f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('utf-8')}",
            mimeType="image/jpeg",
        )
    except Exception as e:
        return e


@mcp.tool()
def inspect_manuscript(md_file: str, page_id: int = 1) -> dict:
    """
    Inspect a specific page from a markdown file.
    Args:
        md_file (str): The path to the markdown file
        page_id (int): The page number to read (1-based index), default is 1
    """
    if not Path(md_file).exists():
        return {"error": f"file does not exist: {md_file}"}
    elif not md_file.lower().endswith(".md"):
        return {"error": f"file is not a markdown file: {md_file}"}
    elif page_id < 1:
        return {"error": "Page ID should be a positive integer starting from 1."}
    markdown = open(md_file).read()
    pages = [p for p in markdown.split("\n---\n") if p.strip()]
    if not len(pages) >= page_id:
        return {
            "error": "Page ID exceeds the number of pages in the document. You could view full content using `read_file` to see if format error happened."
        }
    result = defaultdict(list)
    result["page_id"] = f"{page_id:02d}/{len(pages):02d}"
    result["page_content"] = pages[page_id - 1]

    if re.search(r"!\[.*?\]\(https?://.*?\)", pages[page_id - 1]):
        result["warnings"].append(
            "External image links detected, please downloading and replace them with local paths."
        )

    for match in re.finditer(r"!\[(.*?)\]\((.*?)\)", pages[page_id - 1]):
        label = match.group(1)
        local_path = match.group(2)

        if not Path(local_path).exists():
            result["warnings"].append(
                f"Image file does not exist: {local_path}, please check if there is a format error or file missing."
            )
        count = markdown.count(local_path)
        if not label.strip():
            result["warnings"].append(
                f"Image file {local_path} is missing an alt text label; please add a descriptive label about the image's type, purpose, and content for better accessibility."
            )
        if count != 1:
            result["warnings"].append(
                f"Image file {label}:{local_path} is used {count} times in the document, please check if it's an appropriate usage."
            )

    return result
