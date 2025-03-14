import asyncio
import base64
import re
from typing import Union, List, Dict, Tuple, Optional, Any

from oaib import Auto
from openai import AsyncOpenAI, OpenAI

from utils import get_json_from_response, tenacity


class LLM:
    """
    A wrapper class to interact with a language model.
    """

    def __init__(
        self,
        model: str = "gpt-4o-2024-08-06",
        base_url: str = None,
        api_key: str = None,
    ) -> None:
        """
        Initialize the LLM.

        Args:
            model (str): The model name.
            base_url (str): The base URL for the API.
            api_key (str): API key for authentication. Defaults to environment variable.
        """
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.base_url = base_url

    @tenacity
    def __call__(
        self,
        content: str,
        images: Optional[Union[str, List[str]]] = None,
        system_message: Optional[str] = None,
        history: Optional[List] = None,
        return_json: bool = False,
        return_message: bool = False,
        **client_kwargs,
    ) -> Union[str, Dict, List, Tuple]:
        """
        Call the language model with a prompt and optional images.

        Args:
            content (str): The prompt content.
            images (str or list[str]): An image file path or list of image file paths.
            system_message (str): The system message.
            history (list): The conversation history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.
            **client_kwargs: Additional keyword arguments to pass to the client.

        Returns:
            Union[str, Dict, List, Tuple]: The response from the model.
        """
        if history is None:
            history = []
        system, message = self.format_message(content, images, system_message)
        completion = self.client.chat.completions.create(
            model=self.model, messages=system + history + message, **client_kwargs
        )
        response = completion.choices[0].message.content
        message.append({"role": "assistant", "content": response})
        return self.__post_process__(response, message, return_json, return_message)

    def __post_process__(
        self,
        response: str,
        message: List,
        return_json: bool = False,
        return_message: bool = False,
    ) -> Union[str, Dict, Tuple]:
        """
        Process the response based on return options.

        Args:
            response (str): The raw response from the model.
            message (List): The message history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.

        Returns:
            Union[str, Dict, Tuple]: Processed response.
        """
        if return_json:
            response = get_json_from_response(response)
        if return_message:
            response = (response, message)
        return response

    def __repr__(self) -> str:
        repr_str = f"{self.__class__.__name__}(model={self.model}"
        if self.base_url is not None:
            repr_str += f", base_url={self.base_url}"
        return repr_str + ")"

    def test_connection(self) -> bool:
        """
        Test the connection to the LLM.

        Returns:
            bool: True if connection is successful, False otherwise.
        """
        try:
            self.client.models.list()
            return True
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    def format_message(
        self,
        content: str,
        images: Optional[Union[str, List[str]]] = None,
        system_message: Optional[str] = None,
    ) -> Tuple[List, List]:
        """
        Format messages for OpenAI server call.

        Args:
            content (str): The prompt content.
            images (str or list[str]): An image file path or list of image file paths.
            system_message (str): The system message.

        Returns:
            Tuple[List, List]: Formatted system and user messages.
        """
        if isinstance(images, str):
            images = [images]
        if system_message is None:
            if content.startswith("You are"):
                system_message, content = content.split("\n", 1)
            else:
                system_message = "You are a helpful assistant"
        system = [
            {
                "role": "system",
                "content": [{"type": "text", "text": system_message}],
            }
        ]
        message = [{"role": "user", "content": [{"type": "text", "text": content}]}]
        if images is not None:
            for image in images:
                try:
                    with open(image, "rb") as f:
                        message[0]["content"].append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
                                },
                            }
                        )
                except Exception as e:
                    print(f"Error loading image {image}: {e}")
        return system, message


def get_model_abbr(llms: Union[LLM, List[LLM]]) -> str:
    """
    Get abbreviated model names from LLM instances.

    Args:
        llms: A single LLM instance or a list of LLM instances.

    Returns:
        str: Abbreviated model names joined with '+'.
    """
    # Convert single LLM to list for consistent handling
    if isinstance(llms, LLM):
        llms = [llms]

    try:
        # Attempt to extract model names before version numbers
        return "+".join(re.search(r"^(.*?)-\d{2}", llm.model).group(1) for llm in llms)
    except Exception:
        # Fallback: return full model names if pattern matching fails
        return "+".join(llm.model for llm in llms)


class AsyncLLM(LLM):
    """
    Asynchronous wrapper class for language model interaction.
    """

    def __init__(self, model: str = None, base_url: str = None, api_key: str = None):
        """
        Initialize the AsyncLLM.

        Args:
            model (str): The model name.
            base_url (str): The base URL for the API.
            api_key (str): API key for authentication. Defaults to environment variable.
        """
        self.client = Auto(base_url=base_url, api_key=api_key)
        self.model = model
        self.base_url = base_url
        self.api_key = api_key

    @tenacity
    async def __call__(
        self,
        content: str,
        images: Optional[Union[str, List[str]]] = None,
        system_message: Optional[str] = None,
        history: Optional[List] = None,
        return_json: bool = False,
        return_message: bool = False,
        **client_kwargs,
    ) -> Union[str, Dict, Tuple]:
        """
        Asynchronously call the language model with a prompt and optional images.

        Args:
            content (str): The prompt content.
            images (str or list[str]): An image file path or list of image file paths.
            system_message (str): The system message.
            history (list): The conversation history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.
            **client_kwargs: Additional keyword arguments to pass to the client.

        Returns:
            Union[str, Dict, List, Tuple]: The response from the model.
        """
        if history is None:
            history = []
        system, message = self.format_message(content, images, system_message)
        await self.client.add(
            "chat.completions.create",
            model=self.model,
            messages=system + history + message,
            **client_kwargs,
        )
        completion = await self.client.run()
        response = completion["result"][0]["choices"][0]["message"]["content"]
        assert (
            len(completion["result"]) == 1
        ), "The length of completion result should be 1, but got {}.\nRacing condition may happen, try use `rebuild()` to get a new instance.".format(
            len(completion["result"])
        )
        message.append({"role": "assistant", "content": response})
        return self.__post_process__(response, message, return_json, return_message)

    async def test_connection(self) -> bool:
        """
        Test the connection to the LLM asynchronously.

        Returns:
            bool: True if connection is successful, False otherwise.
        """
        try:
            await self.client.client.models.list()
            return True
        except Exception as e:
            print(f"Async connection test failed: {e}")
            return False

    def rebuild(self) -> "AsyncLLM":
        """
        Create a new instance with the same configuration.

        Returns:
            AsyncLLM: A new instance with the same configuration.
        """
        return AsyncLLM(model=self.model, base_url=self.base_url, api_key=self.api_key)


# Async LLMs should use rebuild in case of racing condition
qwen2_5_async = AsyncLLM(
    model="Qwen2.5-72B-Instruct-GPTQ-Int4", base_url="http://124.16.138.143:7812/v1"
)
qwen_vl_async = AsyncLLM(
    model="Qwen2-VL-7B-Instruct", base_url="http://192.168.14.16:5013/v1"
)
sd3_5_turbo_async = AsyncOpenAI(base_url="http://localhost:8001/v1")

qwen2_5 = LLM(
    model="Qwen2.5-72B-Instruct-GPTQ-Int4", base_url="http://124.16.138.143:7812/v1"
)
qwen_vl = LLM(model="Qwen2-VL-7B-Instruct", base_url="http://192.168.14.16:5013/v1")
sd3_5_turbo = OpenAI(base_url="http://localhost:8001/v1")

# Default models
language_model = qwen2_5
vision_model = qwen_vl
text2image_model = sd3_5_turbo
