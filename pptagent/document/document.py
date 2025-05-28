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
    edit_distance,
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
from .element import Metadata, Section, SubSection, Table, link_medias

logger = get_logger(__name__)

env = Environment(undefined=StrictUndefined)

MERGE_METADATA_PROMPT = env.from_string(
    open(package_join("prompts", "document", "merge_metadata.txt")).read()
)
LITERAL_CONSTRAINT = os.getenv("LITERAL_CONSTRAINT", "false").lower() == "true"


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

    def retrieve(
        self,
        indexs: dict[str, list[str]],
    ) -> list[SubSection]:
        assert isinstance(
            indexs, dict
        ), "subsection_keys for index must be a dict, follow a two-level structure"
        subsecs = []
        for sec_key, subsec_keys in indexs.items():
            section = self[sec_key]
            for subsec_key in subsec_keys:
                subsecs.append(section[subsec_key])
        return subsecs

    def find_caption(self, caption: str):
        for media in self.iter_medias():
            if media.caption == caption:
                return media.path
        raise ValueError(f"Image caption not found: {caption}")

    def get_overview(self, include_summary: bool = False):
        overview = ""
        for section in self.sections:
            overview += f"Section: {section.title}\n"
            if include_summary:
                overview += f"\tSummary: {section.summary}\n"
            for subsection in section.subsections:
                overview += f"\tSubsection: {subsection.title}\n"
                for media in subsection.medias:
                    overview += f"\t\tMedia: {media.caption}\n"
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
    indexs: dict[str, list[str]] | str = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list)

    def model_post_init(self, _):
        """Post-process the model after initialization using ContextVar values."""
        # Get allowed values from context
        allowed_images = _allowed_images.get()
        allowed_indexs = _allowed_indexs.get()

        # Post-process images: find best matches if not exact
        self.images = [
            max(allowed_images, key=lambda x: edit_distance(x, image))
            for image in self.images
        ]

        # Post-process indexs: find best matches for keys and values
        first_levels = list(allowed_indexs.keys())
        for k in list(self.indexs.keys()):
            if k not in first_levels:
                new_key = max(first_levels, key=lambda x: edit_distance(x, k))
                self.indexs[new_key] = self.indexs.pop(k)
            # Second level validation
            for v in self.indexs[k]:
                if v not in allowed_indexs[k]:
                    new_v = max(allowed_indexs[k], key=lambda x: edit_distance(x, v))
                    self.indexs[k][self.indexs[k].index(v)] = new_v

    def retrieve(self, slide_idx: int, document: Document):
        subsections = document.retrieve(self.indexs)
        header = f"Slide-{slide_idx+1}: {self.purpose}\n"
        content = ""
        for subsection in subsections:
            content += f"Paragraph: {subsection.title}\nContent: {subsection.content}\n"
        images = [
            f"Image: {document.find_caption(caption)}\nCaption: {caption}"
            for caption in self.images
        ]
        return header, content, images

    @classmethod
    def response_model(
        cls, allowed_images: list[str], allowed_indexs: dict[str, list[str]]
    ):
        # Set context variables for post-processing
        _allowed_images.set(allowed_images)
        _allowed_indexs.set(allowed_indexs)

        if not LITERAL_CONSTRAINT:
            return cls
        return create_model(
            cls.__name__,
            purpose=(str, Field(...)),
            images=(list[Literal[tuple(allowed_images)]], Field(...)),  # type: ignore
            indexs=(dict[Literal[tuple(allowed_indexs.keys())], list[str]], Field(...)),  # type: ignore
            __base__=BaseModel,
        )
