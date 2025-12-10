from typing import Literal

from appcore import mcp
from firecrawl import Firecrawl

firecrawl_client = Firecrawl()


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
    tbs_map = {
        "month": "qdr:m",
        "year": "qdr:y",
    }

    kwargs = {"query": query, "limit": max_results}
    if time_range:
        kwargs["tbs"] = tbs_map[time_range]

    result = firecrawl_client.search(**kwargs)

    results = [
        {
            "url": item.url,
            "title": item.title,
            "description": item.description,
        }
        for item in result.web
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
    result = firecrawl_client.search(query=query, limit=4, sources=["images"])

    image_results = result.images
    images = [
        {
            "url": item.url,
            "title": item.title,
            "width": item.image_width,
            "height": item.image_height,
        }
        for item in image_results
    ]

    return {
        "query": query,
        "total_results": len(images),
        "images": images,
    }


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(search_images("特朗普"))
    print(result)
    pass
