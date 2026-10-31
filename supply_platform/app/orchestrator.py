"""编排器：按线索当前状态派活给对应智能体。

- 若已安装 langgraph：dispatch(lead_id) 内部由编译后的状态图按 thread_id 驱动
  （每条线索独立状态/会话），节点对应 agent，边按状态条件路由。
- 若未安装 langgraph（或图执行异常）：回退到确定性 switch 实现，保证可运行。

公开签名 dispatch(session, lead_id) 保持不变（main.py 与测试依赖）。
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app import models
from app.agents import data_agent, fulfillment_agent, marketing_agent
from app.state_machine import LeadState, get_state

logger = logging.getLogger("supply.orchestrator")


def _langgraph_enabled() -> bool:
    """langgraph 是否可用（已安装且图编译成功）。"""
    try:
        from app.graph import LANGGRAPH_AVAILABLE, get_graph
        return LANGGRAPH_AVAILABLE and get_graph() is not None
    except Exception:  # pragma: no cover
        return False


def _deterministic_dispatch(session: Session, lead_id: int, state: LeadState) -> dict:
    """确定性派活（langgraph 未启用时的回退实现）。"""
    if state == LeadState.NEW:
        return {"ok": True, "engine": "deterministic", "action": "score",
                "result": data_agent.score_lead(session, lead_id)}
    if state == LeadState.SCORED:
        return {"ok": True, "engine": "deterministic", "action": "outreach",
                "result": marketing_agent.outreach(session, lead_id)}
    if state == LeadState.CONTACTED:
        return {"ok": True, "engine": "deterministic", "action": "await_intent",
                "result": {"note": "已触达，等待意向反馈"}}
    if state == LeadState.INTERESTED:
        return {"ok": True, "engine": "deterministic", "action": "sign",
                "result": fulfillment_agent.sign(session, lead_id)}
    if state == LeadState.SIGNED:
        return {"ok": True, "engine": "deterministic", "action": "ship",
                "result": fulfillment_agent.ship(session, lead_id)}
    if state == LeadState.SHIPPED:
        return {"ok": True, "engine": "deterministic", "action": "done",
                "result": {"note": "已是终态"}}
    return {"ok": False, "reason": f"未知状态 {state}"}


def dispatch(session: Session, lead_id: int) -> dict:
    """依据当前状态派发到对应 agent 的下一步动作。

    优先使用 LangGraph 编排；不可用时回退确定性实现。
    """
    state = get_state(session, lead_id)
    if state is None:
        return {"ok": False, "reason": "线索不存在"}

    # 尝试 LangGraph 编排（每条线索独立会话/状态）
    if _langgraph_enabled():
        try:
            from app.graph import run_for_lead
            return run_for_lead(lead_id)
        except Exception as exc:  # 图执行异常 → 回退确定性，保证健壮
            logger.exception("LangGraph 执行失败，回退确定性实现：%s", exc)

    return _deterministic_dispatch(session, lead_id, state)
