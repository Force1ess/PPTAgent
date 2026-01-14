import asyncio
import json
from itertools import product
from pathlib import Path
from typing import Any

import json_repair
import yaml
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from openai.types.images_response import ImagesResponse
from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from deeppresenter.utils.constants import (
    PACKAGE_DIR,
    PIXEL_MULTIPLE,
    RETRY_TIMES,
)
from deeppresenter.utils.log import debug, logging_openai_exceptions


def get_json_from_response(response: str) -> dict | list:
    """
    Extract JSON from a text response.

    Args:
        response (str): The response text.

    Returns:
        Dict|List: The extracted JSON.

    Raises:
        Exception: If JSON cannot be extracted from the response.
    """

    assert isinstance(response, str) and len(response) > 0, (
        "response must be a non-empty string"
    )
    response = response.strip()
    try:
        return json.loads(response)
    except:
        pass

    # Try to find JSON by looking for matching braces
    open_braces = []
    close_braces = []

    for i, char in enumerate(response):
        if char == "{" or char == "[":
            open_braces.append(i)
        elif char == "}" or char == "]":
            close_braces.append(i)

    for i, j in product(open_braces, reversed(close_braces)):
        if i > j:
            continue
        try:
            json_obj = json.loads(response[i : j + 1])
            if isinstance(json_obj, (dict, list)):
                return max(
                    json_obj, json_repair.loads(response), key=lambda x: len(str(x))
                )
        except Exception:
            pass

    return json_repair.loads(response)


class Endpoint(BaseModel):
    """LLM Endpoint Configuration"""

    base_url: str = Field(description="API base URL")
    model: str = Field(description="Model name")
    api_key: str = Field(description="API key")
    client_kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Client parameters"
    )
    sampling_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Sampling parameters"
    )
    _client: AsyncOpenAI = PrivateAttr()

    def model_post_init(self, _) -> None:
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            **self.client_kwargs,
        )

    async def call(
        self,
        messages: list[dict[str, Any]],
        soft_response_parsing: bool,
        response_format: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        """Execute a chat or tool call using the endpoint client"""
        if tools is not None:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                **self.sampling_parameters,
            )
        elif not soft_response_parsing and response_format is not None:
            response: ChatCompletion = await self._client.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=response_format,
                **self.sampling_parameters,
            )
        else:
            response: ChatCompletion = await self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                **self.sampling_parameters,
            )
        assert response.choices is not None and len(response.choices) > 0, (
            "No choices returned from the model"
        )
        message = response.choices[0].message
        if response_format is not None:
            message.content = response_format(
                **get_json_from_response(message.content)
            ).model_dump_json(indent=2)
        assert tools is None or len(message.tool_calls or []), (
            "No tool call returned from the model"
        )
        assert message.tool_calls or message.content, (
            "Empty content returned from the model"
        )
        return response


class LLM(BaseModel):
    """LLM Client Manager"""

    base_url: str | None = Field(default=None, description="API base URL")
    model: str | None = Field(default=None, description="Model name")
    api_key: str | None = Field(default=None, description="API key")
    identifier: str | None = Field(
        default=None,
        description="Optional identifier for the model instance, this will override property `model_name`",
    )
    is_multimodal: bool | None = Field(
        default=None, description="Whether the model is multimodal"
    )
    max_concurrent: int | None = Field(
        default=None, description="Maximum concurrency limit"
    )
    client_kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Client parameters"
    )
    sampling_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Sampling parameters"
    )
    endpoints: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Additional endpoints for alternating retries",
    )
    soft_response_parsing: bool = Field(
        default=False,
        description="Enable soft parsing: parse response content as JSON directly instead of using completion.parse",
    )
    min_image_size: int | None = Field(
        default=None,
        description="Minimum image size (width * height) for generation, smaller images will be resized proportionally",
    )

    _semaphore: asyncio.Semaphore = PrivateAttr()
    _endpoints: list[Endpoint] = PrivateAttr(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def model_name(self) -> str:
        return self.identifier or self._endpoints[0].model.split("/")[-1].split(":")[0]

    def model_post_init(self, _) -> None:
        """Initialize semaphore and endpoints"""
        self._semaphore = asyncio.Semaphore(self.max_concurrent or 10000)
        if self.model:
            self._endpoints.insert(
                0,
                Endpoint(
                    base_url=self.base_url,
                    model=self.model,
                    api_key=self.api_key,
                    client_kwargs=self.client_kwargs,
                    sampling_parameters=self.sampling_parameters,
                ),
            )
        for endpoint in self.endpoints:
            self._endpoints.append(Endpoint(**endpoint))
        assert len(self._endpoints) >= 1, "At least one endpoint must be configured"

        model_lower = self._endpoints[0].model.lower()
        if self.is_multimodal is None and any(
            word in model_lower for word in ("gpt", "claude", "gemini", "vl")
        ):
            self.is_multimodal = True
            debug(
                f"Model {self._endpoints[0].model} is detected as multimodal model, setting `is_multimodal` to True"
            )

    async def run(
        self,
        messages: list[dict[str, Any]] | str,
        response_format: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
        retry_times: int = RETRY_TIMES,
    ) -> ChatCompletion:
        """Unified interface for chat and tool calls with alternating retry"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        errors = []
        async with self._semaphore:
            for retry_idx in range(retry_times):
                endpoint = self._endpoints[retry_idx % len(self._endpoints)]
                try:
                    return await endpoint.call(
                        messages,
                        self.soft_response_parsing,
                        response_format,
                        tools,
                    )
                except (AssertionError, ValidationError) as e:
                    errors.append(f"[{endpoint.model}] {e}")
                except Exception as e:
                    errors.append(f"[{endpoint.model}] {e}")
                    logging_openai_exceptions(endpoint.model, e)
        raise ValueError(f"All models failed after {retry_times} retries:\n{errors}")

    async def generate_image(
        self,
        prompt: str,
        width: int,
        height: int,
        retry_times: int = RETRY_TIMES,
        pixel_multiple: int = PIXEL_MULTIPLE,
    ) -> ImagesResponse:
        """Unified interface for image generation"""
        if self.min_image_size is not None and (width * height) < int(
            self.min_image_size
        ):
            ratio = (int(self.min_image_size) / (width * height)) ** 0.5
            width = int(width * ratio)
            height = int(height * ratio)
        width = ((width + pixel_multiple - 1) // pixel_multiple) * pixel_multiple
        height = ((height + pixel_multiple - 1) // pixel_multiple) * pixel_multiple
        async with self._semaphore:
            errors = []
            for retry_idx in range(retry_times):
                await asyncio.sleep(retry_idx)
                endpoint = self._endpoints[retry_idx % len(self._endpoints)]
                try:
                    return await endpoint._client.images.generate(
                        prompt=prompt,
                        model=endpoint.model,
                        size=f"{width}x{height}",
                        **endpoint.sampling_parameters,
                    )
                except Exception as e:
                    errors.append(f"[{endpoint.model}] {e}")
                    logging_openai_exceptions(endpoint.model, e)
            raise ValueError(f"All models failed after {retry_times} retries: {errors}")

    async def validate(self):
        endpoint = self._endpoints[0]
        models = await endpoint._client.models.list()
        # ? This for compatibility with google generative ai
        if not any(model.id.endswith(endpoint.model) for model in models.data):
            raise Exception(
                f"Model {endpoint.model} is not available at {endpoint.base_url}, please check your apikey or {PACKAGE_DIR / 'config.yaml'}\n"
            )


class DeepPresenterConfig(BaseModel):
    """DeepPresenter Global Configuration"""

    offline_mode: bool = Field(
        default=False, description="Enable offline mode, disable all network requests"
    )
    file_path: str = Field(description="Configuration file path")
    mcp_config_file: str = Field(
        description="MCP configuration file", default=PACKAGE_DIR / "mcp.json"
    )
    research_agent: LLM = Field(description="Research agent model configuration")
    design_agent: LLM = Field(description="Design agent model configuration")
    long_context_model: LLM = Field(description="Long context model configuration")
    vision_model: LLM = Field(description="Vision model configuration")
    t2i_model: LLM | None = Field(
        default=None, description="Text-to-image model configuration"
    )
    critic_agent: LLM | None = Field(
        default=None, description="Critic agent, used for slide refinement"
    )

    def model_post_init(self, context):
        return super().model_post_init(context)

    @classmethod
    def load_from_file(cls, config_path: str | None = None) -> "DeepPresenterConfig":
        """Load configuration from file"""
        if config_path:
            config_file = Path(config_path)
        else:
            config_file = PACKAGE_DIR / "config.yaml"

        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file {config_file} does not exist")
        config_data = {}
        with open(config_file, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

        config_data["file_path"] = str(config_file.resolve())
        return cls(**config_data)

    async def validate_llms(self):
        # ? t2i endpoints might not support this api
        await asyncio.gather(
            self.research_agent.validate(),
            self.design_agent.validate(),
            self.long_context_model.validate(),
            self.vision_model.validate(),
            self.t2i_model.validate(),
        )

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


GLOBAL_CONFIG = DeepPresenterConfig.load_from_file()
