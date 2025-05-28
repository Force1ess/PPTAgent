from typing import Literal

from pydantic import BaseModel, Field, create_model


class Element(BaseModel):
    name: str
    data: list[str]


class EditorOutput(BaseModel):
    elements: list[Element]

    @property
    def dict(self):
        return {element.name: element.data for element in self.elements}


class LayoutChoice(BaseModel):
    layout: str

    @classmethod
    def response_model(cls, layouts: list[str]):
        return create_model(
            cls.__name__,
            layout=(Literal[tuple(layouts)], Field(...)),
            __base__=BaseModel,
        )
