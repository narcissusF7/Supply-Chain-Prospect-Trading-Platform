"""线索状态机：单一事实源与合法迁移。

状态：NEW → SCORED → CONTACTED → INTERESTED → SIGNED → SHIPPED

设计要点：
- transition() 带 guard：只有"当前状态归属 agent"能发起迁移。
- 幂等：同一 lead 同一目标状态只生效一次（已处于目标状态则 no-op）。
- 并发安全：迁移在 SQLite 事务内完成（SQLite 串行化写，等价于 SELECT...FOR UPDATE）。
- 扩展点：此处为确定性规则引擎；未来可替换为 LangGraph 节点或 LM 编排。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from sqlalchemy.orm import Session

from app import models


class LeadState(str, Enum):
    NEW = "NEW"
    SCORED = "SCORED"
    CONTACTED = "CONTACTED"
    INTERESTED = "INTERESTED"
    SIGNED = "SIGNED"
    SHIPPED = "SHIPPED"


# 各状态归属的 agent（guard 依据）：拥有该状态的 agent 负责其后续迁移
STATE_OWNER: dict[LeadState, str] = {
    LeadState.NEW: "data_agent",
    LeadState.SCORED: "data_agent",
    LeadState.CONTACTED: "marketing_agent",
    LeadState.INTERESTED: "marketing_agent",
    LeadState.SIGNED: "fulfillment_agent",
    LeadState.SHIPPED: "fulfillment_agent",
}

# 合法迁移表：(from, to) -> 允许执行的 agent
TRANSITIONS: dict[tuple[LeadState, LeadState], str] = {
    (LeadState.NEW, LeadState.SCORED): "data_agent",
    (LeadState.SCORED, LeadState.CONTACTED): "marketing_agent",
    (LeadState.CONTACTED, LeadState.INTERESTED): "marketing_agent",
    (LeadState.INTERESTED, LeadState.SIGNED): "fulfillment_agent",
    (LeadState.SIGNED, LeadState.SHIPPED): "fulfillment_agent",
}


@dataclass
class TransitionResult:
    ok: bool
    message: str
    from_state: LeadState | None = None
    to_state: LeadState | None = None


def get_state(session: Session, lead_id: int) -> LeadState | None:
    """读取线索当前状态。"""
    row = session.get(models.LeadState, lead_id)
    if row is None:
        return None
    return LeadState(row.state)


def transition(
    session: Session,
    lead_id: int,
    to_state: LeadState,
    agent: str,
    audit: bool = True,
) -> TransitionResult:
    """执行状态迁移（带 guard 与幂等）。

    行为：
    1. 目标状态等于当前状态 → 幂等 no-op，返回 ok=True（防重复事件）。
    2. 非法迁移（不在 TRANSITIONS） → 拒绝。
    3. agent 非该迁移允许的归属者 → 拒绝（guard）。
    4. 在事务内更新，并写入审计日志（调用方负责 commit，便于组合操作原子化）。
    """
    row = session.get(models.LeadState, lead_id)
    if row is None:
        return TransitionResult(ok=False, message="线索状态不存在", from_state=None, to_state=to_state)

    current = LeadState(row.state)

    # 1) 幂等：已是目标状态，直接返回成功
    if current == to_state:
        return TransitionResult(
            ok=True, message=f"已是 {to_state.value}，幂等跳过",
            from_state=current, to_state=to_state,
        )

    # 2) 合法迁移校验
    allowed_agent = TRANSITIONS.get((current, to_state))
    if allowed_agent is None:
        return TransitionResult(
            ok=False,
            message=f"非法迁移：{current.value} -> {to_state.value} 未被定义",
            from_state=current, to_state=to_state,
        )

    # 3) guard：执行者必须是该迁移的归属 agent
    if agent != allowed_agent:
        return TransitionResult(
            ok=False,
            message=(
                f"guard 拒绝：{current.value} -> {to_state.value} 仅允许 "
                f"{allowed_agent} 执行，当前 {agent}"
            ),
            from_state=current, to_state=to_state,
        )

    # 4) 事务内提交迁移（SQLite 串行化写保证并发安全）
    row.state = to_state.value
    row.current_agent = agent
    row.updated_at = datetime.now()
    session.flush()

    if audit:
        session.add(models.AuditLog(
            event_type="STATE_CHANGE",
            lead_id=lead_id,
            agent=agent,
            detail=f"{current.value} -> {to_state.value}",
        ))

    return TransitionResult(
        ok=True, message=f"迁移成功：{current.value} -> {to_state.value}",
        from_state=current, to_state=to_state,
    )
