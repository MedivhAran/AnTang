"""给「这次为什么是我先开口」写一句人话。

这句话由程序生成，不由模型写：它要说明的是任务为什么被排出来，模型能写得更自然，
但也可能写成诊断、写成指责，或者干脆编一个原因。事实边界放程序这边，措辞留给界面。

字数控制在一条小字能放下，所以只写「哪一类事实」，不复述数值——次数和数值都在
任务证据里，不该出现在患者手机的这一行。行为痕迹那几句刻意不用
`behavior_signals.SIGNAL_LABELS`：那些是给模型看的口径（含窗口与条件），
而这里要的是患者自己能认出来的一句话。
"""

from __future__ import annotations

from antang_api.models import ProactiveCareTask, ProactiveCareTaskKind

ROUTINE_REASON = "到了我们平时说说话的时间"
PLAN_REASON = "你答应过这时候回来说一声"
HEART_HIGH_REASON = "手环记录里刚才有一段心率偏高"
HEART_LOW_REASON = "手环记录里刚才有一段心率偏低"
HEART_OTHER_REASON = "手环记录里刚才有一段和平时不太一样"
SIGNAL_FALLBACK_REASON = "这几天的记录有点不一样"

_SIGNAL_REASONS: dict[str, str] = {
    "repeated_check": "这几天测得比平时密",
    "exercise_avoidance": "你最近好像在躲着运动",
    "night_rechecking": "这几个夜里你常常醒",
}


def message_reason(task: ProactiveCareTask) -> str:
    """按任务来源给出一句可显示的原因；不认识的来源退回一句中性的。"""

    if task.kind == ProactiveCareTaskKind.ROUTINE_CHECK_IN:
        return ROUTINE_REASON
    if task.kind == ProactiveCareTaskKind.PLAN_FOLLOW_UP:
        return PLAN_REASON
    if task.kind == ProactiveCareTaskKind.HEALTH_EVENT:
        direction = (task.health_evidence or {}).get("direction")
        if direction == "high":
            return HEART_HIGH_REASON
        if direction == "low":
            return HEART_LOW_REASON
        return HEART_OTHER_REASON
    if task.kind == ProactiveCareTaskKind.BEHAVIOR_SIGNAL:
        signal = (task.health_evidence or {}).get("signal")
        return _SIGNAL_REASONS.get(str(signal), SIGNAL_FALLBACK_REASON)
    return SIGNAL_FALLBACK_REASON
