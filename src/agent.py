from dataclasses import asdict, dataclass
from functools import partial
from math import ceil

import jsonlines
import tiktoken
import yaml
from FlagEmbedding import BGEM3FlagModel
from jinja2 import Environment, Template
from PIL import Image
from torch import Tensor, cosine_similarity

from llms import LLM, AsyncLLM

ENCODING = tiktoken.encoding_for_model("gpt-4o")
import llms
from model_utils import get_text_embedding
from utils import get_json_from_response, pexists, pjoin


@dataclass
class Turn:
    """
    A class to represent a turn in a conversation.
    """

    id: int
    prompt: str
    response: str
    message: list
    images: list[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    embedding: Tensor = None

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if k != "embedding"}

    def calc_token(self):
        """
        Calculate the number of tokens for the turn.
        """
        if self.images is not None:
            self.input_tokens += calc_image_tokens(self.images)
        self.input_tokens += len(ENCODING.encode(self.prompt))
        self.output_tokens = len(ENCODING.encode(self.response))

    def __eq__(self, other):
        return self is other


class Agent:
    """
    An agent, defined by its instruction template and model.
    """

    def __init__(
        self,
        name: str,
        env: Environment,
        record_cost: bool,
        llm: LLM = None,
        config: dict = None,
        text_model: BGEM3FlagModel = None,
    ):
        """
        Initialize the Agent.

        Args:
            name (str): The name of the role.
            env (Environment): The Jinja2 environment.
            record_cost (bool): Whether to record the token cost.
            llm (LLM): The language model.
            config (dict): The configuration.
            text_model (BGEM3FlagModel): The text model.
        """
        self.name = name
        if config is None:
            with open(f"roles/{name}.yaml", "r") as f:
                config = yaml.safe_load(f)
        if llm is None:
            llm = getattr(llms, config["use_model"] + "_model")
        self.llm = llm
        self.model = llm.model
        self.record_cost = record_cost
        self.text_model = text_model
        self.return_json = config.get("return_json", False)
        self.system_message = config["system_prompt"]
        self.prompt_args = set(config["jinja_args"])
        self.template = env.from_string(config["template"])
        self.retry_template = Template(
            """The previous output is invalid, please carefully analyze the traceback and feedback information, correct errors happened before.
            feedback:
            {{feedback}}
            traceback:
            {{traceback}}
            Give your corrected output in the same format without including the previous output:
            """
        )
        self.input_tokens = 0
        self.output_tokens = 0
        self.history: list[Turn] = []
        run_args = config.get("run_args", {})
        self.llm.__call__ = partial(self.llm.__call__, **run_args)
        self.system_tokens = len(ENCODING.encode(self.system_message))

    def calc_cost(self, turns: list[Turn]):
        """
        Calculate the cost of a list of turns.
        """
        for turn in turns:
            self.input_tokens += turn.input_tokens
            self.output_tokens += turn.output_tokens
        self.input_tokens += self.system_tokens
        self.output_tokens += 3

    def get_history(self, similar: int, recent: int, prompt: str):
        """
        Get the conversation history.
        """
        history = self.history[-recent:] if recent > 0 else []
        if similar > 0:
            embedding = get_text_embedding(prompt, self.text_model)
            history.sort(key=lambda x: cosine_similarity(embedding, x.embedding))
            for turn in history:
                if len(history) > similar + recent:
                    break
                if turn not in history:
                    history.append(turn)
        history.sort(key=lambda x: x.id)
        return history

    def save_history(self, output_dir: str):
        """
        Save the conversation history to a file.
        """
        history_file = pjoin(output_dir, f"{self.name}.jsonl")
        if pexists(history_file) and len(self.history) == 0:
            return
        with jsonlines.open(history_file, "w") as writer:
            writer.write(
                {
                    "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens,
                }
            )
            for turn in self.history:
                writer.write(turn.to_dict())

    def retry(self, feedback: str, traceback: str, error_idx: int):
        """
        Retry a failed turn with feedback and traceback.
        """
        assert error_idx > 0, "error_idx must be greater than 0"
        prompt = self.retry_template.render(feedback=feedback, traceback=traceback)
        history = []
        for turn in self.history[-error_idx:]:
            history.extend(turn.message)
        response, message = self.llm(
            prompt,
            history=history,
            return_message=True,
        )
        turn = Turn(
            id=len(self.history),
            prompt=prompt,
            response=response,
            message=message,
        )
        return self.__post_process__(response, self.history[-error_idx:], turn)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, model={self.model})"

    def __call__(
        self,
        images: list[str] = None,
        recent: int = 0,
        similar: int = 0,
        **jinja_args,
    ):
        """
        Call the agent with prompt arguments.

        Args:
            images (list[str]): A list of image file paths.
            recent (int): The number of recent turns to include.
            similar (int): The number of similar turns to include.
            **jinja_args: Additional arguments for the Jinja2 template.

        Returns:
            The response from the role.
        """
        if isinstance(images, str):
            images = [images]
        assert self.prompt_args == set(jinja_args.keys()), "Invalid arguments"
        prompt = self.template.render(**jinja_args)
        history = self.get_history(similar, recent, prompt)
        history_msg = []
        for turn in history:
            history_msg.extend(turn.message)

        response, message = self.llm(
            prompt,
            system_message=self.system_message,
            history=history_msg,
            images=images,
            return_message=True,
        )
        turn = Turn(
            id=len(self.history),
            prompt=prompt,
            response=response,
            message=message,
            images=images,
        )
        return self.__post_process__(response, history, turn, similar)

    def __post_process__(
        self, response: str, history: list[Turn], turn: Turn, similar: int = 0
    ):
        """
        Post-process the response from the agent.
        """
        self.history.append(turn)
        if similar > 0:
            turn.embedding = get_text_embedding(turn.prompt, self.text_model)
        if self.record_cost:
            turn.calc_token()
            self.calc_cost(history + [turn])
        if self.return_json:
            response = get_json_from_response(response)
        return response


class AsyncAgent(Agent):
    """
    An agent, defined by its instruction template and model.
    """

    def __init__(
        self,
        name: str,
        env: Environment,
        record_cost: bool = True,
        llm: AsyncLLM = None,
        config: dict = None,
        text_model: BGEM3FlagModel = None,
    ):
        super().__init__(name, env, record_cost, llm, config, text_model)
        assert isinstance(self.llm, AsyncLLM), "llm must be an AsyncLLM"
        self.llm = self.llm.rebuild()  # in case of sharing the same instance

    async def retry(self, feedback: str, traceback: str, error_idx: int):
        """
        Retry a failed turn with feedback and traceback.
        """
        assert error_idx > 0, "error_idx must be greater than 0"
        prompt = self.retry_template.render(feedback=feedback, traceback=traceback)
        history = []
        for turn in self.history[-error_idx:]:
            history.extend(turn.message)
        response, message = await self.llm(
            prompt,
            history=history,
            return_message=True,
        )
        turn = Turn(
            id=len(self.history),
            prompt=prompt,
            response=response,
            message=message,
        )
        return self.__post_process__(response, self.history[-error_idx:], turn)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name}, model={self.model})"

    async def __call__(
        self,
        images: list[str] = None,
        recent: int = 0,
        similar: int = 0,
        **jinja_args,
    ):
        """
        Call the agent with prompt arguments.

        Args:
            images (list[str]): A list of image file paths.
            recent (int): The number of recent turns to include.
            similar (int): The number of similar turns to include.
            **jinja_args: Additional arguments for the Jinja2 template.

        Returns:
            The response from the role.
        """
        if isinstance(images, str):
            images = [images]
        assert self.prompt_args == set(jinja_args.keys()), "Invalid arguments"
        prompt = self.template.render(**jinja_args)
        history = self.get_history(similar, recent, prompt)
        history_msg = []
        for turn in history:
            history_msg.extend(turn.message)

        response, message = await self.llm(
            prompt,
            system_message=self.system_message,
            history=history_msg,
            images=images,
            return_message=True,
        )
        turn = Turn(
            id=len(self.history),
            prompt=prompt,
            response=response,
            message=message,
            images=images,
        )
        return self.__post_process__(response, history, turn, similar)


def calc_image_tokens(images: list[str]):
    """
    Calculate the number of tokens for a list of images.
    """
    tokens = 0
    for image in images:
        with open(image, "rb") as f:
            width, height = Image.open(f).size
        if width > 1024 or height > 1024:
            if width > height:
                height = int(height * 1024 / width)
                width = 1024
            else:
                width = int(width * 1024 / height)
                height = 1024
        h = ceil(height / 512)
        w = ceil(width / 512)
        tokens += 85 + 170 * h * w
    return tokens
