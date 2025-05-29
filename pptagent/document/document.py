import asyncio
import os
import re
from contextlib import AsyncExitStack
from contextvars import ContextVar
from typing import Literal, Optional

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, Field, create_model

from pptagent.agent import Agent
from pptagent.llms import AsyncLLM
from pptagent.model_utils import language_id
from pptagent.utils import (
    Language,
    get_logger,
    package_join,
    pbasename,
    pexists,
    pjoin,
)

from .doc_utils import (
    get_tree_structure,
    process_markdown_content,
    split_markdown_by_headings,
)
from .element import Media, Metadata, Section, SubSection, Table, link_medias

logger = get_logger(__name__)

env = Environment(undefined=StrictUndefined)

MERGE_METADATA_PROMPT = env.from_string(
    open(package_join("prompts", "document", "merge_metadata.txt")).read()
)
LITERAL_CONSTRAINT = os.getenv("LITERAL_CONSTRAINT", "false").lower() == "true"


class DocumentIndex(BaseModel):
    section: str
    subsections: list[str]

    @classmethod
    def response_model(cls, section_fields: list[str], subsection_fields: list[str]):
        return create_model(
            cls.__name__,
            section=(Literal[tuple(section_fields)], Field(...)),  # type: ignore
            subsections=(list[Literal[tuple(subsection_fields)]], Field(...)),  # type: ignore
            __base__=BaseModel,
        )


class Document(BaseModel):
    image_dir: str
    language: Language
    metadata: dict[str, str]
    sections: list[Section]

    def validate_medias(self, image_dir: Optional[str] = None):
        if image_dir is not None:
            self.image_dir = image_dir
        assert pexists(
            self.image_dir
        ), f"image directory is not found: {self.image_dir}"
        for media in self.iter_medias():
            if pexists(media.path):
                continue
            basename = pbasename(media.path)
            if pexists(pjoin(self.image_dir, basename)):
                media.path = pjoin(self.image_dir, basename)
            else:
                raise FileNotFoundError(f"image file not found: {media.path}")

    def iter_medias(self):
        for section in self.sections:
            yield from section.iter_medias()

    def get_table(self, image_path: str):
        for media in self.iter_medias():
            if media.path == image_path and isinstance(media, Table):
                return media
        raise ValueError(f"table not found: {image_path}")

    @classmethod
    async def _parse_chunk(
        cls,
        extractor: Agent,
        markdown_chunk: str,
        image_dir: str,
        language_model: AsyncLLM,
        vision_model: AsyncLLM,
        limiter: AsyncExitStack,
    ):
        markdown, medias = process_markdown_content(
            markdown_chunk,
        )
        async with limiter:
            _, section = await extractor(
                markdown_document=markdown,
                response_format=Section.response_model(),
            )
            metadata = section.pop("metadata", {})
            section["content"] = section.pop("subsections")
            section = Section(**section, markdown_content=markdown_chunk)
            link_medias(medias, section)
            for media in section.iter_medias():
                media.parse(image_dir)
                if isinstance(media, Table):
                    await media.get_caption(language_model)
                else:
                    await media.get_caption(vision_model)
        return metadata, section

    @classmethod
    async def from_markdown(
        cls,
        markdown_content: str,
        language_model: AsyncLLM,
        vision_model: AsyncLLM,
        image_dir: str,
        max_at_once: Optional[int] = None,
    ):
        doc_extractor = Agent(
            "doc_extractor",
            llm_mapping={"language": language_model, "vision": vision_model},
        )
        document_tree = get_tree_structure(markdown_content)
        headings = re.findall(r"^#+\s+.*", markdown_content, re.MULTILINE)
        splited_chunks = await split_markdown_by_headings(
            markdown_content, headings, document_tree, language_model
        )

        metadata = []
        sections = []
        tasks = []

        limiter = (
            asyncio.Semaphore(max_at_once)
            if max_at_once is not None
            else AsyncExitStack()
        )
        async with asyncio.TaskGroup() as tg:
            for chunk in splited_chunks:
                tasks.append(
                    tg.create_task(
                        cls._parse_chunk(
                            doc_extractor,
                            chunk,
                            image_dir,
                            language_model,
                            vision_model,
                            limiter,
                        )
                    )
                )

        # Process results in order
        for task in tasks:
            meta, section = task.result()
            metadata.append(meta)
            sections.append(section)

        merged_metadata = await language_model(
            MERGE_METADATA_PROMPT.render(metadata=metadata),
            return_json=True,
            response_format=create_model(
                "MetadataList",
                metadata=(list[Metadata], Field(...)),
                __base__=BaseModel,
            ),
        )
        metadata = {meta["name"]: meta["value"] for meta in merged_metadata["metadata"]}
        return cls(
            image_dir=image_dir,
            language=language_id(markdown_content),
            metadata=metadata,
            sections=sections,
        )

    def __contains__(self, key: str):
        for section in self.sections:
            if section.title == key:
                return True
        return False

    def __getitem__(self, key: str):
        for section in self.sections:
            if section.title == key:
                return section
        raise KeyError(
            f"section not found: {key}, available sections: {[section.title for section in self.sections]}"
        )

    def find_caption(self, caption: str):
        for media in self.iter_medias():
            if media.caption == caption:
                return media.path
        raise ValueError(f"Image caption not found: {caption}")

    def get_overview(self, include_summary: bool = False, include_image: bool = True):
        overview = ""
        for section in self.sections:
            overview += f"<section>{section.title}</section>\n"
            if include_summary:
                overview += f"\tSummary: {section.summary}\n"
            for subsection in section.content:
                if isinstance(subsection, SubSection):
                    overview += f"\t<subsection>{subsection.title}</subsection>\n"
                elif include_image and isinstance(subsection, Media):
                    overview += f"\t<image>{subsection.caption}</image>\n"
            overview += "\n"
        return overview

    @property
    def metainfo(self):
        return "\n".join([f"{k}: {v}" for k, v in self.metadata.items()])


_allowed_images: ContextVar[list[str]] = ContextVar("allowed_images", default=[])
_allowed_indexs: ContextVar[dict[str, list[str]]] = ContextVar(
    "allowed_indexs", default={}
)


class OutlineItem(BaseModel):
    purpose: str
    section: str
    indexes: list[DocumentIndex] | str
    images: list[str] = Field(default_factory=list)

    def retrieve(self, slide_idx: int, document: Document):
        subsections = []
        for index in self.indexes:
            for subsection in index.subsections:
                subsections.append(document[index.section][subsection])
        header = f"Current Slide: {self.purpose}\n"
        header += f"This is the {slide_idx+1} slide of the presentation.\n"
        content = ""
        for subsection in subsections:
            content += f"Paragraph: {subsection.title}\nContent: {subsection.content}\n"
        images = [
            f"<path>{document.find_caption(caption)}</path>: {caption}"
            for caption in self.images
        ]
        return header, content, images

    @classmethod
    def response_model(cls, allowed_images: list[str], document: Document):
        # Set context variables for post-processing
        _allowed_images.set(allowed_images)
        sections = []
        subsections = []
        for sec in document.sections:
            sections.append(sec.title)
            for subsec in sec.content:
                if isinstance(subsec, SubSection):
                    subsections.append(subsec.title)

        return create_model(
            cls.__name__,
            purpose=(str, Field(...)),
            section=(str, Field(...)),
            images=(list[Literal[tuple(allowed_images)]], Field(...)),  # type: ignore
            indexes=(list[DocumentIndex.response_model(sections, subsections)], Field(...)),  # type: ignore
            __base__=BaseModel,
        )


class Outline(BaseModel):
    outline: list[OutlineItem]

    @classmethod
    def response_model(cls, allowed_images: list[str], document: Document):
        return create_model(
            cls.__name__,
            outline=(
                list[OutlineItem.response_model(allowed_images, document)],
                Field(...),
            ),
            __base__=BaseModel,
        )
