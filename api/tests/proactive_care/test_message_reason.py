"""「这次为什么是我先开口」那句话的测试。

这句话给患者看，所以有两件事必须成立：①每类任务都有话说，不认识的来源也要退到
一句中性的；②句子里不能出现次数与数值——数值在我们这边是证据，在他那边就成了
被盯着的感觉。
"""

from __future__ import annotations

import pytest

from antang_api.models import ProactiveCareTask, ProactiveCareTaskKind
from antang_api.proactive_care.reasons import (
    HEART_HIGH_REASON,
    HEART_LOW_REASON,
    HEART_OTHER_REASON,
    PLAN_REASON,
    ROUTINE_REASON,
    SIGNAL_FALLBACK_REASON,
    message_reason,
)


def task(kind: ProactiveCareTaskKind, evidence: dict[str, object] | None = None):
    return ProactiveCareTask(kind=kind, health_evidence=evidence or {})


def test_a_routine_check_in_says_it_is_the_usual_time():
    assert message_reason(task(ProactiveCareTaskKind.ROUTINE_CHECK_IN)) == ROUTINE_REASON


def test_a_plan_follow_up_reminds_him_of_the_promise_not_of_us():
    reason = message_reason(task(ProactiveCareTaskKind.PLAN_FOLLOW_UP))

    assert reason == PLAN_REASON
    assert "答应" in reason


def test_a_heart_rate_event_names_the_direction_it_saw():
    assert (
        message_reason(
            task(ProactiveCareTaskKind.HEALTH_EVENT, {"direction": "high"})
        )
        == HEART_HIGH_REASON
    )
    assert (
        message_reason(
            task(ProactiveCareTaskKind.HEALTH_EVENT, {"direction": "low"})
        )
        == HEART_LOW_REASON
    )
    assert (
        message_reason(task(ProactiveCareTaskKind.HEALTH_EVENT, {}))
        == HEART_OTHER_REASON
    )


@pytest.mark.parametrize(
    ("signal", "expected"),
    [
        ("repeated_check", "这几天测得比平时密"),
        ("exercise_avoidance", "你最近好像在躲着运动"),
        ("night_rechecking", "这几个夜里你常常醒"),
        ("something_new", SIGNAL_FALLBACK_REASON),
        (None, SIGNAL_FALLBACK_REASON),
    ],
)
def test_a_behaviour_signal_borrows_the_label_he_would_recognise(signal, expected):
    evidence = {} if signal is None else {"signal": signal}

    assert message_reason(task(ProactiveCareTaskKind.BEHAVIOR_SIGNAL, evidence)) == expected


@pytest.mark.parametrize(
    "kind",
    [
        ProactiveCareTaskKind.ROUTINE_CHECK_IN,
        ProactiveCareTaskKind.PLAN_FOLLOW_UP,
        ProactiveCareTaskKind.HEALTH_EVENT,
        ProactiveCareTaskKind.BEHAVIOR_SIGNAL,
    ],
)
def test_no_reason_ever_carries_numbers_or_counts(kind):
    reason = message_reason(task(kind, {"direction": "low", "signal": "repeated_check"}))

    assert not any(character.isdigit() for character in reason)
    assert "次" not in reason
