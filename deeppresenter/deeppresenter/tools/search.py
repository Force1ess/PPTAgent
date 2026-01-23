import asyncio
import os
from typing import Any, Literal

import aiohttp
from appcore import mcp
from fake_useragent import UserAgent

from deeppresenter.utils.constants import MAX_RETRY_INTERVAL
from deeppresenter.utils.log import debug, warning

TAVILY_KEYS = [
    i.strip() for i in os.getenv("TAVILY_API_KEY").split(",") if i.startswith("tvly")
]
FAKE_UA = UserAgent()
TAVILY_API_URL = "https://api.tavily.com/search"

debug(f"{len(TAVILY_KEYS)} TAVILY keys loaded")


async def tavily_request(params: dict) -> dict[str, Any]:
    """发送 Tavily API 请求"""
    headers = {"Content-Type": "application/json", "User-Agent": FAKE_UA.random}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            TAVILY_API_URL, headers=headers, json=params
        ) as response:
            if response.status == 429:
                warning("TAVILY rate limit exceeded, waiting...")
                await asyncio.sleep(MAX_RETRY_INTERVAL)
            if response.status != 200:
                warning(
                    f"TAVILY Error [{response.status}] headers={dict(response.headers)} body={await response.text()}"
                )
            response.raise_for_status()
            return await response.json()


async def search_with_fallback(**kwargs) -> dict[str, Any]:
    last_error = None
    for api_key in TAVILY_KEYS:
        try:
            params = {**kwargs, "api_key": api_key}
            return await tavily_request(params)
        except Exception as e:
            warning(f"TAVILY search error with key {api_key[:16]}...: {e}")
            last_error = e

    raise RuntimeError(
        f"TAVILY search failed after {len(TAVILY_KEYS)} retries"
    ) from last_error


@mcp.tool()
async def search_web(
    query: str,
    max_results: int = 3,
    time_range: Literal["month", "year"] | None = None,
) -> dict:
    """
    Search the web

    Args:
        query: Search keywords
        max_results: Maximum number of search results, default 3
        time_range: Time range filter for search results, can be "month", "year", or None

    Returns:
        dict: Dictionary containing search results
    """
    kwargs = {"query": query, "max_results": max_results, "include_images": False}
    if time_range:
        kwargs["time_range"] = time_range

    result = await search_with_fallback(**kwargs)

    results = [
        {
            "url": item["url"],
            "content": item["content"],
        }
        for item in result.get("results", [])
    ]

    return {
        "query": query,
        "total_results": len(results),
        "results": results,
    }


@mcp.tool()
async def search_images(
    query: str,
) -> dict:
    """
    Search for web images
    """
    result = await search_with_fallback(
        query=query,
        max_results=4,
        include_images=True,
        include_image_descriptions=True,
    )

    images = [
        {
            "url": img["url"],
            "description": img["description"],
        }
        for img in result.get("images", [])
    ]

    return {
        "query": query,
        "total_results": len(images),
        "images": images,
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(search_web('Google Gemini model "Gemini 3 Pro" features'))
    print(result)
