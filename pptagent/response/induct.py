from typing import Literal

from pydantic import BaseModel, create_model


class SlideElement(BaseModel):
    el_name: str
    data: list[str]
    el_type: Literal["text", "image"]

    @classmethod
    def response_model(cls, content_fields: list[str]) -> type[BaseModel]:
        ContentLiteral = Literal[tuple(content_fields)]  # type: ignore
        return create_model(
            cls.__name__,
            el_name=(str, ...),
            data=(list[ContentLiteral], ...),
            el_type=(Literal["text", "image"], ...),
            __base__=BaseModel,
        )


class SlideSchema(BaseModel):
    elements: list[SlideElement]

    @classmethod
    def response_model(cls, content_fields: list[str]) -> type[BaseModel]:
        return create_model(
            cls.__name__,
            elements=(list[SlideElement.response_model(content_fields)], ...),
            __base__=BaseModel,
        )
