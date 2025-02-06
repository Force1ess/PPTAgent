import asyncio
import os

import aiohttp
import jsonlines
import tqdm


async def download_file(
    session: aiohttp.ClientSession, filepath: str, url: str
) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    async with session.get(url) as response:
        if response.status == 200:
            with open(filepath, "wb") as f:
                f.write(await response.read())
        elif response.status != 404:
            raise Exception(f"Failed to download {filepath}: {response.status}")


async def main():
    async with aiohttp.ClientSession() as session:
        for record in jsonlines.open("resource/dataset.jsonl", mode="r"):
            filename = record["filename"]
            fp = "pdf" if "/pdf/" in filename else "pptx"
            filename += f"/original.{fp}"
            if not os.path.exists(filename):
                url = record["url"]
                await download_file(session, filename, url)


if __name__ == "__main__":
    asyncio.run(main())
