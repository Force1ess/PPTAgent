from contextvars import ContextVar

from pydantic import BaseModel

from pptagent.utils import edit_distance

# global context variable for allowed headings, used to validate headings in async context
_allowed_headings: ContextVar[list[str]] = ContextVar("allowed_headings", default=[])


class LogicHeadings(BaseModel):
    headings: list[str]

    def model_post_init(self, _):
        self.headings = [
            max(_allowed_headings.get(), key=lambda x: edit_distance(x, h))
            for h in self.headings
        ]

    @classmethod
    def response_model(cls, allowed_headings: list[str]):
        _allowed_headings.set(allowed_headings)
        return cls
