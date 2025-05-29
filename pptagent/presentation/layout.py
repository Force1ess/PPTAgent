import asyncio
from typing import Literal, Optional

from jinja2 import StrictUndefined, Template
from pydantic import BaseModel, field_validator

from pptagent.llms import AsyncLLM
from pptagent.response import EditorOutput
from pptagent.utils import get_logger, package_join, pexists

logger = get_logger(__name__)

LENGTHY_REWRITE_PROMPT = Template(
    open(package_join("prompts", "lengthy_rewrite.txt")).read(),
    undefined=StrictUndefined,
)


class Element(BaseModel):
    name: str
    data: list[str]
    type: Literal["text", "image"]
    suggested_characters: Optional[int] = None
    variable_length: Optional[tuple[int, int]] = None
    variable_data: Optional[dict[str, list[str]]] = None

    def model_post_init(self, _):
        if self.type == "text":
            self.suggested_characters = max(len(i) for i in self.data)

    def get_schema(self):
        schema = f"Element: {self.name}\n"
        schema += f"\tel_type: {self.type}\n"
        if self.type == "text":
            schema += f"\tsuggested_characters: {self.suggested_characters}\n"
        if self.variable_length is not None:
            schema += f"\tThe length of the element can vary between {self.variable_length[0]} and {self.variable_length[1]}\n"
        schema += f"\tThe default quantity of the element is {len(self.data)}\n"
        return schema


class Layout(BaseModel):
    title: str
    template_id: int
    slides: list[int]
    elements: list[Element]
    vary_mapping: Optional[dict[int, int]] = None  # mapping for variable elements

    @field_validator("elements")
    def validate_elements(cls, v):
        num_vary_elements = sum((el.variable_length is not None) for el in v)
        if num_vary_elements > 1:
            raise ValueError("Only one variable element allowed in a layout")
        return v

    def index_template_slide(self, data: EditorOutput):
        old_data = {}
        template_id = self.template_id

        for el in self.elements:
            if el.variable_length is not None:
                num_vary = len(data[el.name].data)
                if not (el.variable_length[0] <= num_vary <= el.variable_length[1]):
                    raise ValueError(
                        f"The length of {el.name}: {num_vary} is not within the allowed range: [{el.variable_length[0]}, {el.variable_length[1]}]"
                    )
                template_id = self.vary_mapping[str(num_vary)]
                key = str(len(data[el.name].data))
                old_data[el.name] = el.variable_data[key]
            else:
                old_data[el.name] = el.data

        return template_id, old_data

    def validate(self, editor_output: EditorOutput):
        for el in editor_output.elements:
            if self[el.name].type != "image":
                continue
            for i in range(len(el.data)):
                if not pexists(el.data[i]):
                    raise ValueError(
                        f"Image {el.data[i]} not found\n"
                        "Please check the image path and use only existing images\n"
                        "Or, leave a blank list for this element"
                    )

    async def length_rewrite(
        self,
        editor_output: EditorOutput,
        length_factor: float,
        language_model: AsyncLLM,
    ):
        async with asyncio.TaskGroup() as tg:
            tasks = []
            for el in editor_output.elements:
                if self[el.name].type != "text":
                    continue
                charater_counts = max([len(i) for i in el.data])
                if charater_counts > self[el.name].suggested_characters * length_factor:
                    task = tg.create_task(
                        language_model(
                            LENGTHY_REWRITE_PROMPT.render(
                                el_name=el.name,
                                content=el.data,
                                suggested_characters=f"{self[el.name].suggested_characters} characters",
                            ),
                            return_json=True,
                        )
                    )
                    tasks.append([el.name, task])

            for el_name, task in tasks:
                editor_output[el_name].data = await task

    @property
    def content_schema(self):
        return "\n".join([el.get_schema() for el in self.elements])

    def remove_item(self, item: str):
        for el in self.elements:
            if item in el.data:
                el.data.remove(item)
                if len(el.data) == 0:
                    self.elements.remove(el)
                return
        else:
            raise ValueError(f"Item {item} not found in layout {self.title}")

    def __contains__(self, key: str | int):
        if isinstance(key, int):
            return key in self.slides
        elif isinstance(key, str):
            for el in self.elements:
                if el.name == key:
                    return True
            return False
        raise ValueError(f"Invalid key type: {type(key)}, should be str or int")

    def __getitem__(self, key: str):
        for el in self.elements:
            if el.name == key:
                return el
        raise ValueError(f"Element {key} not found")

    def __iter__(self):
        return iter(self.elements)

    def __len__(self):
        return len(self.elements)
