import pytest

from llms import qwen2_5_async, qwen2_5


@pytest.mark.asyncio
async def test_asyncllm():
    """
    Test the async LLM connection and functionality.
    """
    # Test connection
    result = await qwen2_5_async.test_connection()
    assert result is True, "Async LLM connection failed"

    # Test response generation
    response = await qwen2_5_async("Hello, how are you?")
    assert response is not None, "Async LLM returned None response"
    assert len(response) > 0, "Async LLM returned empty response"


def test_sync_llm():
    """
    Test the synchronous LLM connection and functionality.
    """
    # Test connection
    result = qwen2_5.test_connection()
    assert result is True, "Sync LLM connection failed"

    # Test response generation
    response = qwen2_5("Hello, how are you?")
    assert response is not None, "Sync LLM returned None response"
    assert len(response) > 0, "Sync LLM returned empty response"