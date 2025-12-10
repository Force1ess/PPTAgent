import os
from typing import Literal

from appcore import mcp
from tavily import TavilyClient, UsageLimitExceededError

from deeppresenter.utils.constants import RETRY_TIMES
from deeppresenter.utils.log import error, warning

tavily_client = TavilyClient()


def search_with_fallback(**kwargs):
    for _ in range(RETRY_TIMES):
        try:
            return tavily_client.search(**kwargs)
        except UsageLimitExceededError as e:
            warning(f"TAVILY APIKEY may out of credits: {os.getenv('TAVILY_API_KEY')}")
            if not os.getenv("TAVILY_BACKUP", None):
                raise e
            return TavilyClient(api_key=os.getenv("TAVILY_BACKUP")).search(**kwargs)
        except Exception as e:
            error(f"TAVILY Error: {e}")
    raise RuntimeError("TAVILY Search Failed after retries")


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

    result = search_with_fallback(**kwargs)

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
    result = search_with_fallback(
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
    pass
