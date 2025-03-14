import asyncio
import base64
import os
import re

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
    ) -> None:
        """
        Initialize the LLM.

        Args:
            model (str): The model name.
            api_base (str): The base URL for the API.
            use_batch (bool): Whether to use OpenAI's Batch API, which is single thread only.
        """
        self.client = OpenAI(base_url=base_url)
        self.model = model
        self.base_url = base_url

    @tenacity
    def __call__(
        self,
        content: str,
        images: list[str] = None,
        system_message: str = None,
        history: list = None,
        return_json: bool = False,
        return_message: bool = False,
        **client_kwargs,
    ) -> str | dict | list:
        """
        Call the language model with a prompt and optional images.

        Args:
            content (str): The prompt content.
            images (list[str]): A list of image file paths.
            system_message (str): The system message.
            history (list): The conversation history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.

        Returns:
            str | dict | list: The response from the model.
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
        message: list,
        return_json: bool = False,
        return_message: bool = False,
    ):
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
        Test the connection to the LLMs.
        """
        try:
            self.client.models.list()
            return True
        except Exception as e:
            print(e)
            return False

    def format_message(
        self,
        content: str,
        images: list[str] = None,
        system_message: str = None,
    ):
        """
        Message formatter for OpenAI server call.
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
            if not isinstance(images, list):
                images = [images]
            for image in images:
                with open(image, "rb") as f:
                    message[0]["content"].append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
                            },
                        }
                    )
        return system, message


def get_model_abbr(llms):
    # Convert single LLM to list for consistent handling
    if isinstance(llms, LLM):
        llms = [llms]

    try:
        # Attempt to extract model names before version numbers
        return "+".join(re.search(r"^(.*?)-\d{2}", llm.model).group(1) for llm in llms)
    except:
        # Fallback: return full model names if pattern matching fails
        return "+".join(llm.model for llm in llms)


class AsyncLLM(LLM):
    def __init__(self, model: str = None, base_url: str = None):
        self.client = Auto(base_url=base_url)
        self.model = model
        self.base_url = base_url

    @tenacity
    async def __call__(
        self,
        content: str,
        images: list[str] = None,
        system_message: str = None,
        history: list = None,
        return_json: bool = False,
        return_message: bool = False,
        **client_kwargs,
    ) -> str | dict | list:
        """
        Call the language model with a prompt and optional images.

        Args:
            content (str): The prompt content.
            images (list[str]): A list of image file paths.
            system_message (str): The system message.
            history (list): The conversation history.
            return_json (bool): Whether to return the response as JSON.
            return_message (bool): Whether to return the message.

        Returns:
            str | dict | list: The response from the model.
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
        assert len(completion["result"]) == 1, "completion result should be 1"
        message.append({"role": "assistant", "content": response})
        return self.__post_process__(response, message, return_json, return_message)

    async def test_connection(self) -> bool:
        """
        Test the connection to the LLMs.
        """
        try:
            await self.client.client.models.list()
            return True
        except Exception as e:
            print(e)
            return False

    def rebuild(self):
        return AsyncLLM(
            model=self.model, base_url=self.base_url
        )


qwen2_5 = AsyncLLM(
    model="Qwen2.5-72B-Instruct-GPTQ-Int4", base_url="http://124.16.138.143:7812/v1"
)
qwen_vl = AsyncLLM(
    model="Qwen2-VL-7B-Instruct", base_url="http://192.168.14.16:5013/v1"
)
sd3_5_turbo = AsyncOpenAI(base_url="http://localhost:8001/v1")
deepseek = AsyncLLM(model="DeepSeek-R1", base_url="http://14.22.75.203:1025/v1")

language_model = qwen2_5
vision_model = qwen_vl
text2image_model = sd3_5_turbo





if __name__ == "__main__":
    async def test_asyncllm():
        print("Connection:", await qwen2_5.test_connection())
        print("Greeting:", await qwen2_5("你好"))
    asyncio.run(test_asyncllm())
