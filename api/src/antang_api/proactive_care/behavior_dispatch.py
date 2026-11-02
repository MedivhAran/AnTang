"""把行为痕迹变成主动关怀任务：算出来、挡住重复的，再排队等 Worker 处理。

这一层只负责「该不该排一个任务」，不负责说什么。说什么由主动关怀 Agent 起草、
Auditor 审核，发多少由每日一条与每周额度管着。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from antang_api.models import (
    GlucoseReading,
    ProactiveCareSettings,
    ProactiveCareTask,
    ProactiveCareTaskKind,
    ProactiveCareTaskStatus,
)
from antang_api.proactive_care.behavior_signals import (
    BehaviorSignal,
    behavior_signals,
)
from antang_api.proactive_care.topics import topic_cooldown_until

BEHAVIOR_SIGNAL_RULE_ID = "behavior_signal"
BEHAVIOR_SIGNAL_RULE_VERSION = "behavior-signal-v1"
# 行为痕迹不是急事：24 小时内都没排上就作废，晚到的问候比没有更糟。
BEHAVIOR_TASK_TTL = timedelta(hours=24)
# 同一类痕迹的话题前缀。冲突检测与话题冷却共用它，所以形状要和心率那条一致。
TOPIC_PREFIX = "behavior"


def behavior_event_key(signal_kind: str) -> str:
    return f"{TOPIC_PREFIX}:{signal_kind}"


async def _queued_for_topic(
    session: AsyncSession, *, user_id: UUID, event_key: str
) -> bool:
    existing = await session.scalar(
        select(ProactiveCareTask.id)
        .where(
            ProactiveCareTask.user_id == user_id,
            ProactiveCareTask.kind == ProactiveCareTaskKind.BEHAVIOR_SIGNAL,
            ProactiveCareTask.health_event_key == event_key,
            ProactiveCareTask.status.in_(
                [
                    ProactiveCareTaskStatus.SCHEDULED,
                    ProactiveCareTaskStatus.RUNNING,
                ]
            ),
        )
        .limit(1)
    )
    return existing is not None


async def queue_behavior_signals(
    session: AsyncSession,
    *,
    user_id: UUID,
    now: datetime | None = None,
    timezone_name: str = "Asia/Shanghai",
) -> list[UUID]:
    """给现在命中的每一条痕迹排一个任务；已经在队里或刚提过的跳过。"""

    moment = now if now is not None else datetime.now(timezone.utc)
    created: list[UUID] = []
    for signal in await behavior_signals(
        session, user_id=user_id, now=moment, timezone_name=timezone_name
    ):
        event_key = behavior_event_key(signal.kind)
        if await _queued_for_topic(session, user_id=user_id, event_key=event_key):
            continue
        resumes_at = await topic_cooldown_until(
            session, user_id=user_id, prefix=event_key, now=moment
        )
        due_at = resumes_at if resumes_at is not None else moment
        expires_at = due_at + BEHAVIOR_TASK_TTL
        if due_at > moment + BEHAVIOR_TASK_TTL:
            # 冷却还没结束就已经过了有效期：这次不提，等下次算出来再说。
            continue
        task = ProactiveCareTask(
            user_id=user_id,
            kind=ProactiveCareTaskKind.BEHAVIOR_SIGNAL,
            status=ProactiveCareTaskStatus.SCHEDULED,
            due_at=due_at,
            expires_at=expires_at,
            health_event_key=event_key,
            health_evidence=signal.as_dict(),
            rule_id=BEHAVIOR_SIGNAL_RULE_ID,
            rule_version=BEHAVIOR_SIGNAL_RULE_VERSION,
        )
        session.add(task)
        await session.flush()
        created.append(task.id)
    return created


async def sweep_behavior_signals(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> list[UUID]:
    """扫一遍最近有血糖记录、且开着健康事件的用户，给命中的排任务。

    只扫「最近一天里有读数」的人：没有新数据的人不会凭空多出痕迹，扫他等于浪费
    一次查询。
    """

    moment = now if now is not None else datetime.now(timezone.utc)
    since = moment - timedelta(hours=24)
    user_ids = (
        await session.scalars(
            select(distinct(GlucoseReading.user_id))
            .join(
                ProactiveCareSettings,
                ProactiveCareSettings.user_id == GlucoseReading.user_id,
            )
            .where(
                GlucoseReading.measured_at >= since,
                GlucoseReading.measured_at <= moment,
                GlucoseReading.revoked_at.is_(None),
                ProactiveCareSettings.health_events_enabled.is_(True),
            )
            .limit(limit)
        )
    ).all()
    created: list[UUID] = []
    for user_id in user_ids:
        settings = await session.get(ProactiveCareSettings, user_id)
        if settings is None:
            continue
        created.extend(
            await queue_behavior_signals(
                session,
                user_id=user_id,
                now=moment,
                timezone_name=settings.timezone,
            )
        )
    return created


def signal_from_task_evidence(
    evidence: dict[str, object] | None,
) -> BehaviorSignal | None:
    """从任务里存的证据还原一条痕迹，用来核对「这一刻还成不成立」。"""

    if not evidence:
        return None
    kind = evidence.get("kind")
    label = evidence.get("label")
    occurred = evidence.get("occurred")
    window_days = evidence.get("window_days")
    if (
        not isinstance(kind, str)
        or not isinstance(label, str)
        or not isinstance(occurred, int)
        or not isinstance(window_days, int)
    ):
        return None
    return BehaviorSignal(
        kind=kind,
        label=label,
        occurred=occurred,
        window_days=window_days,
        evidence=(),
    )


__all__ = [
    "BEHAVIOR_SIGNAL_RULE_ID",
    "BEHAVIOR_SIGNAL_RULE_VERSION",
    "BEHAVIOR_TASK_TTL",
    "TOPIC_PREFIX",
    "behavior_event_key",
    "queue_behavior_signals",
    "signal_from_task_evidence",
    "sweep_behavior_signals",
]
