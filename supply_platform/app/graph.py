"""LangGraph 编排：将 MVP 确定性派活升级为状态图编排。

设计意图（落地"3 独立 agent 会话 + 按状态派活"）
------------------------------------------------
- 每个 lead 以 thread_id = str(lead_id) 独立运行一张状态图，实现"每条线索独立状态/会话"。
- 图中每个节点对应一个 agent 的单一动作；节点内部调用对应 agent，并调用
  state_machine.transition 推进状态（guard / 幂等 / 事务由 state_machine 保证）。
- 边使用 conditional edges，依据 lead 当前状态（从 DB 实时读取）决定下一节点；
  非法/无效迁移会被 state_machine.transition 的 guard 拒绝，节点据此安全停在 END。

节点与状态映射
--------------
- collect_node  : NEW       采集/归一化边界（真实采集由 data_agent.collect / /collect 完成）
- score_node    : SCORED    评分分层（data_agent.score_lead：NEW→SCORED）
- outreach_node : CONTACTED 触达（marketing_agent.outreach：SCORED→CONTACTED，内部已过合规）
- intent_node   : INTERESTED 标记意向（marketing_agent guard：CONTACTED→INTERESTED）
- sign_node     : SIGNED    签约（fulfillment_agent.sign：INTERESTED→SIGNED）
- ship_node     : SHIPPED   发货（fulfillment_agent.ship：SIGNED→SHIPPED）

会话隔离：三个 agent 各自在节点内使用独立 DB 会话（SessionLocal），体现隔离会话设计。

依赖：langgraph 为可选；未安装时 orchestrator 自动回退确定性实现，保证可运行。
"""
from __future__ import annotations

import logging
from typing import TypedDict

from app import models
from app.db import SessionLocal
from app.state_machine import LeadState

logger = logging.getLogger("supply.graph")

# 尝试导入 langgraph；未安装则 LANGGRAPH_AVAILABLE=False，orchestrator 走回退路径。
try:  # pragma: no cover - 取决于是否安装 langgraph
    from langgraph.checkpoint.memory import MemorySaver  # type: ignore
    from langgraph.graph import END, START, StateGraph  # type: ignore
    LANGGRAPH_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.warning("langgraph 未安装，编排将回退确定性实现：%s", exc)
    LANGGRAPH_AVAILABLE = False
    END = "__end__"  # type: ignore
    START = "__start__"  # type: ignore
    StateGraph = None  # type: ignore
    MemorySaver = None  # type: ignore


class GraphState(TypedDict, total=False):
    """图状态：至少含 lead_id；trace 记录各节点执行轨迹。"""
    lead_id: int
    last_event: str
    trace: list


def _current_state(lead_id: int) -> LeadState | None:
    """从 DB 实时读取线索当前状态。"""
    from app.state_machine import get_state
    with SessionLocal() as session:
        return get_state(session, lead_id)


# ---------------- 节点 ----------------


def collect_node(state: GraphState) -> GraphState:
    lead_id = state["lead_id"]
    logger.info("[graph] collect_node lead=%s", lead_id)
    with SessionLocal() as session:
        lead = session.get(models.Lead, lead_id)
        if lead is None:
            return {
                **state,
                "last_event": f"collect: lead {lead_id} 不存在",
                "trace": state.get("trace", []) + [{"node": "collect", "ok": False, "reason": "线索不存在"}],
            }
    return {
        **state,
        "last_event": "collect done",
        "trace": state.get("trace", []) + [{"node": "collect", "ok": True}],
    }


def score_node(state: GraphState) -> GraphState:
    lead_id = state["lead_id"]
    from app.agents import data_agent
    logger.info("[graph] score_node lead=%s", lead_id)
    with SessionLocal() as session:
        res = data_agent.score_lead(session, lead_id)
    return {
        **state,
        "last_event": f"score: {res}",
        "trace": state.get("trace", []) + [{"node": "score", "ok": res.get("ok", False), "detail": res}],
    }


def outreach_node(state: GraphState) -> GraphState:
    lead_id = state["lead_id"]
    from app.agents import marketing_agent
    logger.info("[graph] outreach_node lead=%s", lead_id)
    with SessionLocal() as session:
        res = marketing_agent.outreach(session, lead_id)
    return {
        **state,
        "last_event": f"outreach: {res}",
        "trace": state.get("trace", []) + [{"node": "outreach", "ok": res.get("ok", False), "detail": res}],
    }


def intent_node(state: GraphState) -> GraphState:
    lead_id = state["lead_id"]
    from app.state_machine import transition
    logger.info("[graph] intent_node lead=%s", lead_id)
    with SessionLocal() as session:
        res = transition(session, lead_id, LeadState.INTERESTED, agent="marketing_agent", audit=True)
        session.commit()
    return {
        **state,
        "last_event": f"intent: {res.message}",
        "trace": state.get("trace", []) + [{"node": "intent", "ok": res.ok, "detail": res.message}],
    }


def sign_node(state: GraphState) -> GraphState:
    lead_id = state["lead_id"]
    from app.agents import fulfillment_agent
    logger.info("[graph] sign_node lead=%s", lead_id)
    with SessionLocal() as session:
        res = fulfillment_agent.sign(session, lead_id)
    return {
        **state,
        "last_event": f"sign: {res}",
        "trace": state.get("trace", []) + [{"node": "sign", "ok": res.get("ok", False), "detail": res}],
    }


def ship_node(state: GraphState) -> GraphState:
    lead_id = state["lead_id"]
    from app.agents import fulfillment_agent
    logger.info("[graph] ship_node lead=%s", lead_id)
    with SessionLocal() as session:
        res = fulfillment_agent.ship(session, lead_id)
    return {
        **state,
        "last_event": f"ship: {res}",
        "trace": state.get("trace", []) + [{"node": "ship", "ok": res.get("ok", False), "detail": res}],
    }


# ---------------- 路由（conditional edges） ----------------


def entry_router(state: GraphState) -> str:
    """START：按当前状态路由到对应节点；SHIPPED/未知 → END。"""
    st = _current_state(state["lead_id"])
    if st is None:
        return END
    mapping = {
        LeadState.NEW: "collect_node",
        LeadState.SCORED: "score_node",
        LeadState.CONTACTED: "intent_node",
        LeadState.INTERESTED: "sign_node",
        LeadState.SIGNED: "ship_node",
        LeadState.SHIPPED: END,
    }
    return mapping[st]


def _route_score(state: GraphState) -> str:
    return "outreach_node" if _current_state(state["lead_id"]) == LeadState.SCORED else END


def _route_intent(state: GraphState) -> str:
    return "sign_node" if _current_state(state["lead_id"]) == LeadState.INTERESTED else END


def _route_sign(state: GraphState) -> str:
    return "ship_node" if _current_state(state["lead_id"]) == LeadState.SIGNED else END


# ---------------- 编译图 ----------------


def _build_graph():
    if not LANGGRAPH_AVAILABLE or StateGraph is None:
        return None
    builder = StateGraph(GraphState)
    builder.add_node("collect_node", collect_node)
    builder.add_node("score_node", score_node)
    builder.add_node("outreach_node", outreach_node)
    builder.add_node("intent_node", intent_node)
    builder.add_node("sign_node", sign_node)
    builder.add_node("ship_node", ship_node)

    builder.add_conditional_edges(START, entry_router)
    builder.add_edge("collect_node", "score_node")
    builder.add_conditional_edges("score_node", _route_score)
    builder.add_edge("outreach_node", END)
    builder.add_conditional_edges("intent_node", _route_intent)
    builder.add_conditional_edges("sign_node", _route_sign)
    builder.add_edge("ship_node", END)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


_GRAPH = _build_graph() if (LANGGRAPH_AVAILABLE and StateGraph is not None) else None


def get_graph():
    """返回编译后的状态图（未安装 langgraph 时为 None）。"""
    return _GRAPH


def run_for_lead(lead_id: int) -> dict:
    """按 thread_id=str(lead_id) 运行图（每条线索独立会话/状态）。"""
    graph = get_graph()
    if graph is None:
        return {"ok": False, "engine": "none", "reason": "langgraph 未启用"}
    result = graph.invoke(
        {"lead_id": lead_id, "trace": []},
        config={"configurable": {"thread_id": str(lead_id)}},
    )
    return {
        "ok": True,
        "engine": "langgraph",
        "thread_id": str(lead_id),
        "trace": result.get("trace", []),
        "last_event": result.get("last_event", ""),
    }
