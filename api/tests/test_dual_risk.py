"""双风险：把「血糖危不危险」与「他说没说感觉到」分开记。

测三件事：危险的低值配「没感觉」时标签是 `silent`；只说感觉、数字给了也能算；
没有数字就不许猜；标签和档位落库的样子。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from langchain.tools import ToolRuntime
from langchain_core.tools import StructuredTool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from antang_api.agents.runtime import AgentContext
from antang_api.chat import prepare_chat_run
from antang_api.models import (
    PersonalProfile,
    ProactiveCareSettings,
    RiskAnnotation,
    User,
)
from antang_api.psychosocial.dual_risk import (
    classify_label,
    describe,
    physiological_risk,
    render_dual_risk_context,
)
from antang_api.tools.dual_risk import RECORD_DUAL_RISK_TOOL_NAME, build_dual_risk_tool


class _Sessions:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> _Sessions:
        return self

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _coroutine(tool: Any) -> Callable[..., Awaitable[dict[str, object]]]:
    assert isinstance(tool, StructuredTool)
    return cast(Callable[..., Awaitable[dict[str, object]]], tool.coroutine)


def _runtime(user_id: UUID, run_id: UUID | None = None) -> ToolRuntime[AgentContext]:
    return ToolRuntime(
        state={"messages": []},
        context=AgentContext(
            user_id=user_id,
            run_id=run_id if run_id is not None else uuid4(),
            input_message_count=1,
        ),
        config={},
        stream_writer=lambda _value: None,
        tool_call_id="dual-risk-call",
        store=None,
        tools=[],
    )


async def _create_user(session: AsyncSession, prefix: str) -> User:
    username = f"{prefix}_{uuid4().hex[:10]}"
    user = User(
        username=username,
        username_normalized=username,
        password_hash="test-only-password-hash",
    )
    session.add(user)
    await session.flush()
    session.add(ProactiveCareSettings(user_id=user.id))
    await session.flush()
    return user


@pytest.mark.parametrize(
    ("value_mg_dl", "expected"),
    [
        (40, "high"),
        (53, "high"),
        (54, "moderate"),
        (69, "moderate"),
        (70, "none"),
        (140, "none"),
        (180, "none"),
        (181, "moderate"),
        (251, "high"),
    ],
)
def test_the_thresholds_are_the_ones_the_plan_says(
    value_mg_dl: int, expected: str
) -> None:
    assert (
        physiological_risk(value_mg_dl, target_low_mg_dl=70, target_high_mg_dl=180)
        == expected
    )


def test_the_patients_own_target_decides_what_counts_as_off() -> None:
    # 他自己把范围设成 80–160 之后，78 就算偏低（虽然 78 不到 3.9）。
    assert (
        physiological_risk(78, target_low_mg_dl=80, target_high_mg_dl=160)
        == "moderate"
    )


@pytest.mark.parametrize(
    ("physiological", "felt", "label"),
    [
        ("high", "strong", "both"),
        ("moderate", "some", "both"),
        ("high", "none", "silent"),
        ("moderate", "none", "silent"),
        ("none", "strong", "felt_only"),
        ("none", "some", "felt_only"),
        ("none", "none", "neither"),
    ],
)
def test_the_label_says_which_of_the_two_is_high(
    physiological: str, felt: str, label: str
) -> None:
    assert classify_label(physiological, felt) == label


def test_a_nonsense_pick_is_refused() -> None:
    with pytest.raises(ValueError, match="没有这种生理风险档"):
        classify_label("panic", "none")
    with pytest.raises(ValueError, match="没有这种感受档"):
        describe("none", "terrified")


def test_the_context_lines_do_not_turn_them_into_conclusions() -> None:
    class _Row:
        label = "silent"
        measured_at = datetime(2026, 10, 30, 3, 10, tzinfo=timezone.utc)

    rendered = render_dual_risk_context(cast(Any, [_Row()]))

    assert "10-30 03:10 血糖危险，他没感觉到" in rendered
    assert "不要拿来当结论" in rendered


@pytest.mark.asyncio
async def test_a_low_reading_he_did_not_feel_is_marked_silent(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "dual_silent")
    prepared_run = await prepare_chat_run(db_session, user.id, uuid4(), "刚测了 2.9")
    await db_session.commit()
    tool = _coroutine(build_dual_risk_tool(cast(Any, _Sessions(db_session))))

    recorded = await tool(
        runtime=_runtime(user.id, prepared_run.run_id),
        felt_risk="none",
        value_mmol=2.9,
        measured_at="2026-11-02T03:10:00+08:00",
        note="说没什么感觉",
    )

    assert recorded["recorded"] is True
    assert recorded["label"] == "silent"
    assert recorded["label_text"] == "血糖危险，他没感觉到"
    assert recorded["linked_reading"] is False

    stored = (await db_session.scalars(select(RiskAnnotation))).one()
    assert stored.physiological_risk == "high"
    assert stored.felt_risk == "none"
    assert stored.source_message_id == prepared_run.user_message_id
    assert stored.measured_at == datetime(2026, 11, 1, 19, 10, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_a_number_inside_his_own_range_but_scary_is_felt_only(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "dual_felt")
    profile = PersonalProfile(
        user_id=user.id,
        glucose_target_low_mg_dl=80,
        glucose_target_high_mg_dl=160,
    )
    db_session.add(profile)
    await db_session.commit()
    tool = _coroutine(build_dual_risk_tool(cast(Any, _Sessions(db_session))))

    recorded = await tool(runtime=_runtime(user.id), felt_risk="strong", value_mmol=5.2)

    assert recorded["label"] == "felt_only"
    assert recorded["physiological"] == "血糖不在危险范围"


@pytest.mark.asyncio
async def test_without_a_number_the_tool_asks_for_one_first(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session, "dual_nonum")
    tool = _coroutine(build_dual_risk_tool(cast(Any, _Sessions(db_session))))

    with pytest.raises(ValueError, match="要先把血糖数字记下来"):
        await tool(runtime=_runtime(user.id), felt_risk="some")

    assert list((await db_session.scalars(select(RiskAnnotation))).all()) == []


@pytest.mark.asyncio
async def test_a_time_without_a_timezone_is_refused(db_session: AsyncSession) -> None:
    user = await _create_user(db_session, "dual_naive")
    tool = _coroutine(build_dual_risk_tool(cast(Any, _Sessions(db_session))))

    with pytest.raises(ValueError, match="时间要带时区"):
        await tool(
            runtime=_runtime(user.id),
            felt_risk="some",
            value_mmol=6.1,
            measured_at="2026-11-02T03:10:00",
        )


@pytest.mark.asyncio
async def test_another_patients_reading_cannot_be_linked(db_session: AsyncSession) -> None:
    owner = await _create_user(db_session, "dual_owner")
    stranger = await _create_user(db_session, "dual_stranger")
    from antang_api.health_profile.glucose import record_glucose_reading

    theirs = await record_glucose_reading(
        db_session,
        user_id=stranger.id,
        value_mg_dl=60,
        measured_at=datetime.now(timezone.utc) - timedelta(hours=1),
        context="fasting",
        source="fingerstick",
    )
    await db_session.commit()
    tool = _coroutine(build_dual_risk_tool(cast(Any, _Sessions(db_session))))

    with pytest.raises(ValueError, match="找不到这条血糖读数"):
        await tool(
            runtime=_runtime(owner.id),
            felt_risk="none",
            glucose_reading_id=str(theirs.id),
        )


def test_the_tool_name_is_stable() -> None:
    session = cast(AsyncSession, object())
    tool = build_dual_risk_tool(cast(Any, _Sessions(session)))

    assert tool.name == RECORD_DUAL_RISK_TOOL_NAME
    assert set(tool.args) == {
        "felt_risk",
        "value_mmol",
        "glucose_reading_id",
        "measured_at",
        "note",
    }
