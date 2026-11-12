from collections.abc import AsyncIterator
from typing import Any

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_openai import ChatOpenAI

from antang_api import llm


class _Empty:
    """模拟中转站只回一个空分片。"""

    def __init__(self) -> None:
        self.calls = 0

    async def astream(
        self,
        input: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessageChunk]:
        self.calls += 1
        yield AIMessageChunk(content="")


@pytest.fixture()
def empty_then_text(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    state = {"calls": 0}

    async def fake_astream(
        self: ChatOpenAI,
        input: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessageChunk]:
        state["calls"] += 1
        if state["calls"] == 1:
            yield AIMessageChunk(content="")
            return
        yield AIMessageChunk(content="先坐下")
        yield AIMessageChunk(content="，吃点糖。")

    monkeypatch.setattr(ChatOpenAI, "astream", fake_astream)
    return state


@pytest.mark.asyncio()
async def test_an_empty_stream_is_asked_again(empty_then_text: dict[str, int]) -> None:
    model = llm._build_model(streaming=True)

    chunks = [chunk async for chunk in model.astream([("human", "你好")])]

    assert empty_then_text["calls"] == 2
    assert "".join(str(chunk.content) for chunk in chunks) == "先坐下，吃点糖。"


@pytest.mark.asyncio()
async def test_it_gives_up_after_three_empty_streams() -> None:
    model = llm._build_model(streaming=True)
    calls = {"count": 0}

    async def always_empty(
        self: ChatOpenAI,
        input: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessageChunk]:
        calls["count"] += 1
        yield AIMessageChunk(content="")

    original = ChatOpenAI.astream
    ChatOpenAI.astream = always_empty  # type: ignore[method-assign]
    try:
        chunks = [chunk async for chunk in model.astream([("human", "你好")])]
    finally:
        ChatOpenAI.astream = original  # type: ignore[method-assign]

    assert calls["count"] == llm.EMPTY_STREAM_ATTEMPTS
    assert "".join(str(chunk.content) for chunk in chunks) == ""


@pytest.mark.asyncio()
async def test_a_tool_call_counts_as_an_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    async def tool_call_only(
        self: ChatOpenAI,
        input: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[AIMessageChunk]:
        calls["count"] += 1
        yield AIMessageChunk(
            content="",
            tool_calls=[
                {"name": "record_glucose", "args": {"value_mmol": 6.4}, "id": "call_1"}
            ],
        )

    monkeypatch.setattr(ChatOpenAI, "astream", tool_call_only)
    model = llm._build_model(streaming=True)

    chunks = [chunk async for chunk in model.astream([("human", "记一下 6.4")])]

    assert calls["count"] == 1
    assert chunks[0].tool_calls
