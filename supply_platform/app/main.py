"""FastAPI 应用入口。

启动时建表（init_db）。挂载各 REST 端点。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, seed as seed_module
from app.agents import data_agent, fulfillment_agent, marketing_agent
from app.channels import kdniao_logistics
from app.config_store import get_all, set_all
from app.db import SessionLocal, get_db, init_db
from app.orchestrator import dispatch
from app.schemas import (
    AuditOut,
    ContractOut,
    FulfillmentOrderOut,
    GenericOut,
    HealthOut,
    LeadOut,
    SettingsOut,
    SettingsUpdate,
    SignRequest,
    ShipRequest,
)
from app.state_machine import LeadState, transition

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 应用启动：建表（幂等）
    init_db()
    yield


app = FastAPI(title="Supply Platform MVP", version="0.1.0", lifespan=lifespan)


@app.get("/api/v1/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(status="ok")


@app.post("/api/v1/seed", response_model=GenericOut)
def do_seed(db: Session = Depends(get_db)) -> GenericOut:
    result = seed_module.seed(db)
    return GenericOut(ok=True, detail=str(result))


@app.post("/api/v1/collect", response_model=GenericOut)
def do_collect(db: Session = Depends(get_db)) -> GenericOut:
    leads = data_agent.collect(db)
    return GenericOut(ok=True, detail=f"collected {len(leads)} leads")


@app.post("/api/v1/score", response_model=GenericOut)
def do_score(db: Session = Depends(get_db)) -> GenericOut:
    results = data_agent.score_all(db)
    return GenericOut(ok=True, detail=f"scored {len(results)} leads")


@app.get("/api/v1/leads", response_model=list[LeadOut])
def list_leads(
    state: str | None = Query(None),
    tier: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[LeadOut]:
    stmt = select(models.Lead).join(models.LeadState, models.Lead.id == models.LeadState.lead_id)
    if state:
        stmt = stmt.where(models.LeadState.state == state)
    if tier:
        stmt = stmt.where(models.Lead.tier == tier)
    leads = db.execute(stmt).scalars().all()
    return [LeadOut.from_model(l) for l in leads]


@app.post("/api/v1/outreach", response_model=GenericOut)
def do_outreach(
    channel: str = Query("SMS"),
    db: Session = Depends(get_db),
) -> GenericOut:
    # 对全部 SCORED 线索触达（内部必过合规中间件）
    stmt = (
        select(models.Lead)
        .join(models.LeadState, models.Lead.id == models.LeadState.lead_id)
        .where(models.LeadState.state == LeadState.SCORED.value)
    )
    leads = db.execute(stmt).scalars().all()
    results = [marketing_agent.outreach(db, l.id, channel=channel) for l in leads]
    return GenericOut(ok=True, detail=str(results))


@app.post("/api/v1/leads/{lead_id}/intent", response_model=GenericOut)
def mark_intent(lead_id: int, db: Session = Depends(get_db)) -> GenericOut:
    # CONTACTED -> INTERESTED（guard: marketing_agent）
    lead = db.get(models.Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="线索不存在")
    result = transition(db, lead_id, LeadState.INTERESTED, agent="marketing_agent", audit=True)
    db.commit()
    return GenericOut(ok=result.ok, detail=result.message)


@app.get("/api/v1/audit", response_model=list[AuditOut])
def list_audit(db: Session = Depends(get_db)) -> list[AuditOut]:
    stmt = select(models.AuditLog).order_by(models.AuditLog.id.desc())
    logs = db.execute(stmt).scalars().all()
    return [AuditOut.from_model(a) for a in logs]


@app.post("/api/v1/dispatch/{lead_id}", response_model=GenericOut)
def do_dispatch(lead_id: int, db: Session = Depends(get_db)) -> GenericOut:
    # 演示用：按当前状态派活
    result = dispatch(db, lead_id)
    return GenericOut(ok=result.get("ok", False), detail=str(result))


@app.post("/api/v1/leads/{lead_id}/sign", response_model=GenericOut)
def do_sign(
    lead_id: int, body: SignRequest, db: Session = Depends(get_db),
) -> GenericOut:
    """签约（INTERESTED → SIGNED）。失败（如状态非法被 guard 拦截）返回 400。"""
    result = fulfillment_agent.sign(
        db, lead_id, signer_name=body.signer_name, signer_phone=body.signer_phone,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("message") or result.get("reason") or "签约失败",
        )
    return GenericOut(ok=True, detail=result.get("message", "签约成功"))


@app.post("/api/v1/leads/{lead_id}/ship", response_model=GenericOut)
def do_ship(
    lead_id: int, body: ShipRequest, db: Session = Depends(get_db),
) -> GenericOut:
    """发货（SIGNED → SHIPPED）。失败（如状态非法被 guard 拦截）返回 400。"""
    result = fulfillment_agent.ship(
        db, lead_id, sku=body.sku, qty=body.qty,
        receiver_name=body.receiver_name, receiver_phone=body.receiver_phone,
        receiver_address=body.receiver_address,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=result.get("message") or result.get("reason") or "发货失败",
        )
    return GenericOut(ok=True, detail=result.get("message", "发货成功"))


@app.get("/api/v1/contracts", response_model=list[ContractOut])
def list_contracts(db: Session = Depends(get_db)) -> list[ContractOut]:
    """合同列表（按 id 倒序）。"""
    stmt = select(models.Contract).order_by(models.Contract.id.desc())
    return [ContractOut.from_model(c) for c in db.execute(stmt).scalars().all()]


@app.get("/api/v1/orders", response_model=list[FulfillmentOrderOut])
def list_orders(db: Session = Depends(get_db)) -> list[FulfillmentOrderOut]:
    """履约物流单列表（按 id 倒序）。"""
    stmt = select(models.FulfillmentOrder).order_by(models.FulfillmentOrder.id.desc())
    return [FulfillmentOrderOut.from_model(o) for o in db.execute(stmt).scalars().all()]


@app.get("/api/v1/leads/{lead_id}/tracking")
def get_tracking(lead_id: int, db: Session = Depends(get_db)) -> dict:
    """查询该 lead 最新履约单的物流轨迹。

    无履约单 / 无物流单返回 {ok:False, reason:"无物流单"}；
    否则返回 query_tracking 结果（provider/status/tracking_no/traces）。
    """
    order = db.execute(
        select(models.FulfillmentOrder)
        .where(models.FulfillmentOrder.lead_id == lead_id)
        .order_by(models.FulfillmentOrder.id.desc())
    ).scalars().first()
    if order is None or not order.tracking_no:
        return {"ok": False, "reason": "无物流单"}
    return kdniao_logistics.query_tracking(order.tracking_no)


# ---------------- 系统设置（采集 / 评分 / 合规 可视化配置） ----------------


def _sanitize_compliance(compliance: dict) -> dict:
    """对合规配置做轻量校验与钳制，避免非法数值写入。"""
    out = dict(compliance)
    # 呼叫时段：0–23，且 start < end
    start = int(out.get("call_start_hour", 9))
    end = int(out.get("call_end_hour", 21))
    start = max(0, min(23, start))
    end = max(0, min(23, end))
    if end <= start:
        end = min(23, start + 1)
    out["call_start_hour"] = start
    out["call_end_hour"] = end
    # 频次：窗口 >= 1 天，上限 >= 1 次
    out["frequency_window_days"] = max(1, int(out.get("frequency_window_days", 7)))
    out["frequency_cap"] = max(1, int(out.get("frequency_cap", 3)))
    return out


@app.get("/api/v1/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)) -> SettingsOut:
    """读取全量系统配置（采集 / 评分 / 合规）。未配置段回退默认值。"""
    cfg = get_all(db)
    return SettingsOut(**cfg)


@app.put("/api/v1/settings", response_model=SettingsOut)
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db)) -> SettingsOut:
    """更新系统配置（按段部分更新，仅接受已知字段）。

    写入后评分 / 合规 / 采集逻辑立即读取新值生效。
    """
    payload: dict = {}
    if body.collection is not None:
        payload["collection"] = body.collection
    if body.scoring is not None:
        payload["scoring"] = body.scoring
    if body.compliance is not None:
        payload["compliance"] = _sanitize_compliance(body.compliance)
    if not payload:
        raise HTTPException(status_code=400, detail="未提供任何配置段")
    cfg = set_all(db, payload)
    db.commit()
    return SettingsOut(**cfg)
