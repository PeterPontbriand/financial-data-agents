from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.client import LLMClient, LLMGenerateResult


def test_llm_client_init() -> None:
    """Verify LLMClient initializes cleanly."""
    client = LLMClient(base_url="http://example.com")
    assert client is not None


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_llm_client_generate_success(mock_post: AsyncMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "response": "Hello world",
        "prompt_eval_count": 11,
        "eval_count": 3,
    }
    mock_post.return_value = mock_response

    client = LLMClient(base_url="http://example.com")
    messages = [{"role": "user", "content": "Hello world"}]

    result = await client.generate(messages)

    assert isinstance(result, LLMGenerateResult)
    assert result.text == "Hello world"
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 3


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_llm_client_generate_missing_usage(mock_post: AsyncMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "Hello world"}
    mock_post.return_value = mock_response

    client = LLMClient(base_url="http://example.com")
    result = await client.generate([{"role": "user", "content": "hi"}])

    assert result.text == "Hello world"
    assert result.prompt_tokens is None
    assert result.completion_tokens is None


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_llm_client_generate_with_schema_format(mock_post: AsyncMock) -> None:
    """format=<dict> is forwarded as a top-level body key."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": '{"tool_name": "get_price"}'}
    mock_post.return_value = mock_response

    schema = {
        "type": "object",
        "properties": {"tool_name": {"type": "string"}},
        "required": ["tool_name"],
    }

    client = LLMClient(base_url="http://example.com")
    await client.generate(
        [{"role": "user", "content": "Get price"}],
        model="llama3",
        temperature=0.1,
        format=schema,
    )

    mock_post.assert_awaited_once()
    body = mock_post.call_args.kwargs["json"]
    assert body["format"] == schema
    assert body["messages"] == [{"role": "user", "content": "Get price"}]
    assert body["target_model"] == "llama3"
    assert body["options"]["temperature"] == 0.1
    # `format` must NOT be nested under options.
    assert "format" not in body["options"]


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_llm_client_generate_with_json_string_format(mock_post: AsyncMock) -> None:
    """format="json" (string) is forwarded verbatim."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "{}"}
    mock_post.return_value = mock_response

    client = LLMClient(base_url="http://example.com")
    await client.generate([{"role": "user", "content": "hi"}], format="json")

    body = mock_post.call_args.kwargs["json"]
    assert body["format"] == "json"
    assert "format" not in body["options"]


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_llm_client_generate_omits_format_when_none(mock_post: AsyncMock) -> None:
    """When format is None, the body must not contain a format key."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "hello"}
    mock_post.return_value = mock_response

    client = LLMClient(base_url="http://example.com")
    await client.generate([{"role": "user", "content": "hi"}])

    body = mock_post.call_args.kwargs["json"]
    assert "format" not in body
    assert "format" not in body["options"]
    assert "messages" in body
    assert "target_model" in body
    assert "options" in body
