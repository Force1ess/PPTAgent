import asyncio
import json
import traceback
from itertools import product
from pathlib import Path
from typing import Any

import json_repair
import yaml
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from openai.types.images_response import ImagesResponse
from pydantic import BaseModel, Field, PrivateAttr, ValidationError

from deeppresenter.utils.constants import MIN_IMAGE_SIZE, PACKAGE_DIR, RETRY_TIMES
from deeppresenter.utils.log import debug, error, logging_openai_exceptions


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


class LLM(BaseModel):
    """LLM Client Manager"""

    base_url: str = Field(description="API base URL")
    model: str = Field(description="Model name")
    api_key: str = Field(description="API key")
    is_multimodal: bool = Field(
        default=False, description="Whether the model is multimodal"
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
    soft_response_parsing: bool = Field(
        default=False,
        description="Enable soft parsing: parse response content as JSON directly instead of using completion.parse",
    )

    # Fallback configuration
    fallback_base_url: str | None = Field(
        default=None, description="Fallback API base URL"
    )
    fallback_model: str | None = Field(default=None, description="Fallback model name")
    fallback_api_key: str | None = Field(default=None, description="Fallback API key")
    fallback_client_kwargs: dict[str, Any] = Field(
        default_factory=dict, description="Fallback client parameters"
    )
    fallback_sampling_parameters: dict[str, Any] = Field(
        default_factory=dict, description="Fallback sampling parameters"
    )

    _semaphore: asyncio.Semaphore = PrivateAttr()
    _client: AsyncOpenAI = PrivateAttr()
    _fallback_client: AsyncOpenAI | None = PrivateAttr(default=None)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def model_name(self) -> str:
        if "/" in self.model:
            return self.model.split("/")[-1]
        return self.model

    @property
    def has_fallback(self) -> bool:
        """Check if fallback is configured"""
        return all(
            [
                self.fallback_base_url,
                self.fallback_model,
                self.fallback_api_key,
            ]
        )

    def model_post_init(self, _) -> None:
        """Initialize semaphore and clients"""
        self._semaphore = asyncio.Semaphore(self.max_concurrent or 10000)
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            **self.client_kwargs,
        )

        # 初始化 fallback client
        if self.has_fallback:
            self._fallback_client = AsyncOpenAI(
                api_key=self.fallback_api_key,
                base_url=self.fallback_base_url,
                **self.fallback_client_kwargs,
            )

        model_lower = self.model.lower()
        if not self.is_multimodal and any(
            word in model_lower for word in ("gpt", "claude", "gemini", "vl")
        ):
            self.is_multimodal = True
            debug(
                f"Model {self.model} is detected as multimodal model, setting `is_multimodal` to True"
            )

    async def _call(
        self,
        client: AsyncOpenAI,
        model: str,
        messages: list[dict[str, Any]],
        sampling_params: dict[str, Any],
        response_format: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
        retry_times: int = RETRY_TIMES,
    ) -> ChatCompletion:
        """Execute chat or tool call using the specified client"""
        for retry_idx in range(retry_times):
            await asyncio.sleep(2**retry_idx - 1)
            try:
                if tools is not None:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        **sampling_params,
                    )
                elif not self.soft_response_parsing and response_format is not None:
                    response: ChatCompletion = await client.chat.completions.parse(
                        model=model,
                        messages=messages,
                        response_format=response_format,
                        **sampling_params,
                    )
                else:
                    response: ChatCompletion = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        **sampling_params,
                    )
                assert response.choices is not None and len(response.choices) > 0, (
                    "No choices returned from the model"
                )
                message = response.choices[0].message
                if response_format is not None:
                    message.content = response_format(
                        **get_json_from_response(message.content)
                    ).model_dump_json(indent=2)
                assert tools is None or len(message.tool_calls), (
                    "No tool call returned from the model"
                )
                assert message.tool_calls or message.content, (
                    "Empty content returned from the model"
                )
                return response
            except (AssertionError, ValidationError):
                pass
            except Exception as e:
                logging_openai_exceptions(model, e)
        error(f"Model {model} failed for: {traceback.format_exc()}")
        raise ValueError(f"{model} cannot get valid response from the model")

    async def run(
        self,
        messages: list[dict[str, Any]] | str,
        response_format: type[BaseModel] | None = None,
        tools: list[dict[str, Any]] | None = None,
        retry_times: int = RETRY_TIMES,
    ) -> ChatCompletion:
        """Unified interface for chat and tool calls"""
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        async with self._semaphore:
            try:
                return await self._call(
                    self._client,
                    self.model,
                    messages,
                    self.sampling_parameters,
                    response_format,
                    tools,
                    retry_times,
                )
            except Exception as e:
                if self._fallback_client is not None:
                    debug(
                        f"Primary model {self.model} failed, trying fallback model {self.fallback_model}"
                    )
                    return await self._call(
                        self._fallback_client,
                        self.fallback_model,
                        messages,
                        self.fallback_sampling_parameters,
                        response_format,
                        tools,
                        retry_times,
                    )
                raise e

    async def generate_image(
        self,
        prompt: str,
        width: int,
        height: int,
        retry_times: int = RETRY_TIMES,
    ) -> ImagesResponse:
        """Unified interface for image generation"""
        if MIN_IMAGE_SIZE is not None and (width * height) < int(MIN_IMAGE_SIZE):
            ratio = (int(MIN_IMAGE_SIZE) / (width * height)) ** 0.5
            width = int(width * ratio)
            height = int(height * ratio)
        width = ((width + 15) // 16) * 16
        height = ((height + 15) // 16) * 16
        async with self._semaphore:
            for retry_idx in range(retry_times):
                await asyncio.sleep(retry_idx)
                try:
                    return await self._client.images.generate(
                        prompt=prompt,
                        model=self.model,
                        size=f"{width}x{height}",
                        **self.sampling_parameters,
                    )
                except Exception as e:
                    logging_openai_exceptions(self.model, e)
            raise ValueError("Cannot generate image")

    async def validate(self):
        models = await self._client.models.list()
        # ? This for compatibility with google generative ai
        if not any(model.id.endswith(self.model) for model in models.data):
            raise Exception(
                f"Model {self.model} is not available at {self.base_url}, please check your apikey or {PACKAGE_DIR / 'config.yaml'}\n"
            )


class DeepPresenterConfig(BaseModel):
    """DeepPresenter Global Configuration"""

    mcp_config_file: str = Field(
        description="MCP configuration file", default=PACKAGE_DIR / "mcp.json"
    )
    research_agent: LLM = Field(description="Research agent model configuration")
    design_agent: LLM = Field(description="Design agent model configuration")
    long_context_model: LLM = Field(description="Long context model configuration")
    vision_model: LLM = Field(description="Vision model configuration")
    t2i_model: LLM = Field(description="Text-to-image model configuration")

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

        return cls(**config_data)

    async def validate_llms(self):
        # ? we do not valite t2i model since some providers like volcengine did not open this endpoint
        await asyncio.gather(
            self.research_agent.validate(),
            self.design_agent.validate(),
            self.long_context_model.validate(),
            self.vision_model.validate(),
        )

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


GLOBAL_CONFIG = DeepPresenterConfig.load_from_file()
