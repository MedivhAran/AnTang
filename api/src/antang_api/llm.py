from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessageChunk, BaseMessageChunk
from langchain_openai import ChatOpenAI

from antang_api.settings import settings

EMPTY_STREAM_ATTEMPTS = 3
"""上游偶尔回一个空的流（没文字、没工具调用）。多试两次，别让患者看到「回复失败」。"""


class ResilientChatOpenAI(ChatOpenAI):
    """把「空的流」当成一次没发生过的调用。

    中转站（pro.gemai.cc）会随机返回只有一个空分片的流：`choices: []` 加
    `[DONE]`，模型一个字都没说。这种情况下上游没有任何副作用，重放同一请求是
    安全的——工具调用、写库这些副作用发生在 Agent 层，不在模型调用里。

    成功（有文字或工具调用）时把攒下的分片原样吐出去，所以调用方看到的仍是
    一个正常的流，只是这一次多等了几秒。
    """

    async def astream(  # type: ignore[override]
        self,
        input: Any,
        config: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[BaseMessageChunk]:
        for attempt in range(EMPTY_STREAM_ATTEMPTS):
            collected: list[BaseMessageChunk] = []
            text_length = 0
            has_tool_call = False

            async for chunk in super().astream(input, config=config, **kwargs):
                collected.append(chunk)
                if isinstance(chunk, AIMessageChunk):
                    if chunk.text:
                        text_length += len(chunk.text)
                    if chunk.tool_calls:
                        has_tool_call = True

            if text_length or has_tool_call or attempt == EMPTY_STREAM_ATTEMPTS - 1:
                for chunk in collected:
                    yield chunk
                return


def _build_model(*, streaming: bool, model_name: str | None = None) -> ChatOpenAI:
    return ResilientChatOpenAI(
        model=model_name or settings.hachimi_model_name,
        api_key=settings.hachimi_api_key,
        base_url=settings.hachimi_openai_base_url,
        timeout=settings.hachimi_timeout_seconds,
        max_completion_tokens=settings.hachimi_max_output_tokens,
        max_retries=0,
        streaming=streaming,
        stream_usage=streaming,
    )


def build_chat_model() -> ChatOpenAI:
    """创建用于 Core Agent 用户可见流式回复的模型。"""

    return _build_model(streaming=True)


def build_non_streaming_model() -> ChatOpenAI:
    """创建用于内部 Sub-agent、不会向聊天流发送 token 的模型。"""

    return _build_model(streaming=False)


def build_proactive_care_model() -> ChatOpenAI:
    """创建主动关怀 worker 使用的模型。

    对话和主动关怀可以各自选模型：对话再慢用户也能追问，主动关怀是深夜自己
    发出去的，所以宁可让它慢一点，也别换一个质量更差的。没配
    HACHIMI_PROACTIVE_MODEL_NAME 时回退到对话模型。
    """

    return _build_model(
        streaming=False,
        model_name=settings.resolved_proactive_model_name,
    )
