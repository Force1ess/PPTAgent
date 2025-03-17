from abc import abstractmethod
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, List, Optional, Dict
from uuid import uuid4

from llms import LLM
from utils import markdown_table_to_image


@dataclass
class Media:
    markdown_content: str
    path: Optional[str] = None

    @abstractmethod
    def get_caption(self, llm: LLM):
        pass

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        assert (
            "markdown_content" in data
        ), f"'markdown_content' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        return cls(
            markdown_content=data["markdown_content"], path=data.get("path", None)
        )


class Picture(Media):
    def get_caption(self, llm: LLM):
        return super().get_caption(llm)


class Table(Media):
    def __init__(self, markdown_content: str, path: Optional[str] = None):
        self.markdown_content = markdown_content
        self.path = path

    def get_caption(self, llm: LLM):
        return super().get_caption(llm)

    def get_path(self):
        if self.path is None:
            self.path = f"table_{uuid4()[:4]}.png"
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
            "title" in data
        ), f"'title' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        assert (
            "content" in data
        ), f"'content' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        media = data.get("media", None)
        if media is not None:
            media = Media.from_dict(media)
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
            "title" in data
        ), f"'title' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        assert (
            "subsections" in data
        ), f"'subsections' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        return cls(
            title=data["title"],
            subsections=[
                SubSection.from_dict(subsection) for subsection in data["subsections"]
            ],
        )


@dataclass
class Document:
    def __init__(self, sections: List[Section], metadata: Dict[str, Any]):
        self.sections = sections
        self.metadata = metadata

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        assert (
            "sections" in data
        ), f"'sections' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        assert (
            "metadata" in data
        ), f"'metadata' key is required in data dictionary but was not found. Available keys: {list(data.keys())}"
        return cls(
            sections=[Section.from_dict(section) for section in data["sections"]],
            metadata=data["metadata"],
        )

    def __str__(self):
        return str(asdict(self))

    @property
    def metadata(self):
        meta_data = "\n".join([f"{k}: {v}" for k, v in self.metadata.items()])
        return (
            f"{meta_data}\nPresentation Time: {datetime.now().strftime('%Y-%m-%d')}\n"
        )

    @property
    def overview(self):
        return {
            "sections": [
                {
                    "title": section.title,
                    "subsections": [
                        subsection.title for subsection in section.subsections
                    ],
                }
                for section in self.sections
            ]
        }

    @property
    def image_dir(self):
        return self.metadata.get("image_dir", None)

if __name__ == "__main__":
    import json

    with open("test_pdf/refined_doc.json", "r") as f:
        data = json.load(f)
    document = Document.from_dict(data)

    print(document)
