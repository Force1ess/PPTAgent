from dataclasses import dataclass, asdict
import PIL
from datetime import datetime
from typing import Any, List, Optional, Dict
from uuid import uuid4
import asyncio

from markdown import markdown
from bs4 import BeautifulSoup
from jinja2 import Environment, StrictUndefined

from llms import LLM, AsyncLLM
from utils import markdown_table_to_image, pjoin, pexists

env = Environment(undefined=StrictUndefined)
TABLE_CAPTION_PROMPT = env.from_string(
    open("prompts/markdown_table_caption.txt").read()
)
IMAGE_CAPTION_PROMPT = env.from_string(
    open("prompts/markdown_image_caption.txt").read()
)
REFINE_TEMPLATE = env.from_string(open("prompts/document_refine.txt").read())


@dataclass
class Media:
    markdown_content: str
    markdown_caption: str
    path: Optional[str] = None
    caption: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        assert (
            "markdown_content" in data and "markdown_caption" in data
        ), f"'markdown_content' and 'markdown_caption' keys are required in data dictionary but were not found. Available keys: {list(data.keys())}"
        return cls(
            markdown_content=data["markdown_content"],
            markdown_caption=data["markdown_caption"],
            path=data.get("path", None),
            caption=data.get("caption", None),
        )

    @property
    def size(self):
        assert self.path is not None, "Path is required to get size"
        return PIL.Image.open(self.path).size


class Table(Media):
    def to_image(self, image_dir: str):
        if self.path is None:
            self.path = pjoin(image_dir, f"table_{uuid4()[:4]}.png")
        markdown_table_to_image(self.markdown_content, self.path)
        return self.path


@dataclass
class SubSection:
    title: str
    content: str
    media: Optional[Media] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        assert (
            "title" in data and "content" in data
        ), f"'title' and 'content' keys are required in data dictionary but were not found. Available keys: {list(data.keys())}"
        media = data.get("media", None)
        if media is not None:
            if media.get("path", None) is not None:
                media = Media.from_dict(media)
            else:
                media = Table.from_dict(media)
        return cls(
            title=data["title"],
            content=data["content"],
            media=media,
        )


@dataclass
class Section:
    title: str
    subsections: List[SubSection]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        assert (
            "title" in data and "subsections" in data
        ), f"'title' and 'subsections' keys are required in data dictionary but were not found. Available keys: {list(data.keys())}"
        return cls(
            title=data["title"],
            subsections=[
                SubSection.from_dict(subsection) for subsection in data["subsections"]
            ],
        )

    def __getitem__(self, key: str):
        for subsection in self.subsections:
            if subsection.title == key:
                return subsection
        raise KeyError(f"subsection not found: {key}")


@dataclass
class Document:
    sections: List[Section]
    metadata: Dict[str, str]

    def __init__(
        self,
        image_dir: str,
        metadata: Dict[str, str],
        sections: List[Section],
    ):
        self.sections = sections
        self.image_dir = image_dir
        self.metadata = metadata
        self.metadata["presentation_time"] = datetime.now().strftime("%Y-%m-%d")

    def iter_medias(self):
        for section in self.sections:
            for subsection in section.subsections:
                if subsection.media is not None:
                    yield subsection.media

    def validate_medias(self, require_caption: bool = True):
        for media in self.iter_medias():
            if media.path is not None and not pexists(media.path):
                if pexists(pjoin(self.image_dir, media.path)):
                    media.path = pjoin(self.image_dir, media.path)
                else:
                    raise FileNotFoundError(
                        f"image file not found: {media.path}, leave null for table elements and real path for image elements"
                    )
            assert (
                media.caption is not None or not require_caption
            ), f"caption is required for media: {media.path}"

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], image_dir: str, require_caption: bool = True
    ):
        assert (
            "sections" in data
        ), f"'sections' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        assert (
            "metadata" in data
        ), f"'metadata' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        document = cls(
            sections=[Section.from_dict(section) for section in data["sections"]],
            metadata=data["metadata"],
            image_dir=image_dir,
        )
        document.validate_medias(require_caption)
        return document

    @classmethod
    def from_markdown(
        cls,
        markdown_content: str,
        language_model: LLM,
        vision_model: LLM,
        image_dir: str,
    ):
        markdown_html= markdown(markdown_content, extensions=["tables"])
        soup = BeautifulSoup(markdown_html, "html.parser")
        num_medias = len(soup.find_all("img")) + len(soup.find_all("table"))
        doc_json = language_model(
            REFINE_TEMPLATE.render(markdown_document=markdown_content), return_json=True
        )
        document = Document.from_dict(doc_json, image_dir, False)
        assert num_medias == len(list(document.iter_medias())), "number of media elements does not match"
        for media in document.iter_medias():
            if isinstance(media, Table):
                media.to_image(image_dir)
                media.caption = language_model(
                    TABLE_CAPTION_PROMPT.render(
                        markdown_content=media.markdown_content,
                        markdown_caption=media.markdown_caption,
                    )
                )
            else:
                media.caption = vision_model(
                    IMAGE_CAPTION_PROMPT.render(
                        markdown_caption=media.markdown_caption,
                    ),
                    media.path,
                )
        return document

    @classmethod
    async def from_markdown_async(
        cls,
        markdown_content: str,
        language_model: AsyncLLM,
        vision_model: AsyncLLM,
        image_dir: str,
    ):
        markdown_html= markdown(markdown_content, extensions=["tables"])
        soup = BeautifulSoup(markdown_html, "html.parser")
        num_medias = len(soup.find_all("img")) + len(soup.find_all("table"))
        doc_json = await language_model(
            REFINE_TEMPLATE.render(markdown_document=markdown_content), return_json=True
        )
        document = Document.from_dict(doc_json, image_dir)
        assert num_medias == len(list(document.iter_medias())), "number of media elements does not match"

        caption_tasks = []
        media_list = []

        for media in document.iter_medias():
            if isinstance(media, Table):
                media.to_image(image_dir)
                task = language_model(
                    TABLE_CAPTION_PROMPT.format(
                        markdown_content=media.markdown_content,
                        markdown_caption=media.markdown_caption,
                    )
                )
            else:
                task = vision_model(
                    IMAGE_CAPTION_PROMPT.format(
                        markdown_caption=media.markdown_caption,
                    ),
                    images=media.path,
                )
            caption_tasks.append(task)
            media_list.append(media)

        captions = await asyncio.gather(*caption_tasks)
        for media, caption in zip(media_list, captions):
            media.caption = caption

        return document

    def __getitem__(self, key: str):
        for section in self.sections:
            if section.title == key:
                return section
        raise KeyError(f"section not found: {key}")

    def to_dict(self):
        return asdict(self)

    def index(self, subsection_keys: dict[str, list[str]])-> List[SubSection]:
        subsecs = []
        for sec_key, subsec_keys in subsection_keys.items():
            section = self[sec_key]
            for subsec_key in subsec_keys:
                subsecs.append(section[subsec_key])
        return subsecs

    @property
    def metainfo(self):
        return "\n".join([f"{k}: {v}" for k, v in self._metadata.items()])

    @property
    def overview(self):
        overview = self.to_dict()
        for section in overview["sections"]:
            for subsection in section["subsections"]:
                subsection.pop("content")
        return overview

@dataclass
class OutlineItem:
    title: str
    description: str
    indexs: Dict[str, List[str]]

    def retrieve(self, document: Document):
        return document.index(self.indexs)

if __name__ == "__main__":
    import json
    import llms

    with open("test_pdf/source.md", "r") as f:
        markdown_content = f.read()
    image_dir = "test_pdf"
    document = Document.from_markdown(
        markdown_content, llms.language_model, llms.vision_model, image_dir
    )

    print(document)
