"""Fulfillment Agent（履约智能体）。

职责边界：
- sign：INTERESTED → SIGNED，调用法大大电子签约通道（真实 / mock 回退），落库 Contract
       与审计，迁移状态。
- ship：SIGNED → SHIPPED，调用 WMS 出库 + 快递鸟物流下单，落库 FulfillmentOrder 与审计，
       迁移状态。

通道设计（严格沿用 aliyun_sms 的回退范式）：
- 真实通道位于 app.channels（fadada_esign / wms / kdniao_logistics），均实现
  is_configured() + 真实路径 + mock 回退 + 异常兜底；无凭据时本地必跑通。
- 状态机 guard 要求 INTERESTED→SIGNED 与 SIGNED→SHIPPED 均由 fulfillment_agent 执行；
  若 lead 当前状态不合法，transition 会拒绝，message 透传给调用方（ok=False）。
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.channels import fadada_esign, kdniao_logistics, wms
from app.state_machine import LeadState, transition

logger = logging.getLogger("supply.fulfillment_agent")


def sign(
    session: Session,
    lead_id: int,
    signer_name: str = "",
    signer_phone: str = "",
) -> dict:
    """签约：INTERESTED → SIGNED。

    流程：查线索 → 法大大签约通道（真实 / mock 回退）拿到 contract_no / contract_url /
          provider → 落库 Contract（status=SIGNED，填 signed_at）→ 写审计 SIGN →
          状态迁移（guard: fulfillment_agent）→ commit。

    若线索当前非 INTERESTED，transition 的 guard 会拒绝，本函数回滚未提交事务并将
    message 透传给调用方（ok=False，不落库合同）。
    """
    lead = session.get(models.Lead, lead_id)
    if lead is None:
        return {"ok": False, "reason": "线索不存在"}

    receipt = fadada_esign.send_contract(
        lead, signer_name=signer_name, signer_phone=signer_phone,
    )
    contract_no = receipt.get("contract_no", "")
    contract_url = receipt.get("contract_url", "")
    provider = receipt.get("provider", "mock")

    contract = models.Contract(
        lead_id=lead_id,
        contract_no=contract_no,
        signer_name=signer_name,
        signer_phone=signer_phone,
        contract_url=contract_url,
        provider=provider,
        status="SIGNED",
        signed_at=datetime.now(),
    )
    session.add(contract)
    session.flush()  # 拿到 contract.id，供后续履约单反查

    session.add(models.AuditLog(
        event_type="SIGN", lead_id=lead_id, agent="fulfillment_agent",
        detail=f"contract_no={contract_no}; provider={provider}; url={contract_url}",
    ))

    # 状态迁移（guard: fulfillment_agent；INTERESTED → SIGNED）
    result = transition(session, lead_id, LeadState.SIGNED, agent="fulfillment_agent", audit=True)
    if not result.ok:
        # 迁移被 guard 拒绝：回滚未提交事务（不落库合同 / 审计），透传 message
        session.rollback()
        logger.warning("[FULFILLMENT] 签约状态迁移被拒绝：%s", result.message)
        return {"ok": False, "message": result.message, "reason": result.message}

    session.commit()
    return {
        "ok": True,
        "message": "签约成功",
        "contract_no": contract_no,
        "contract_url": contract_url,
        "provider": provider,
    }


def ship(
    session: Session,
    lead_id: int,
    sku: str = "DEFAULT",
    qty: int = 1,
    receiver_name: str = "",
    receiver_phone: str = "",
    receiver_address: str = "",
) -> dict:
    """发货：SIGNED → SHIPPED。

    流程：查线索 → WMS 出库（真实 / mock 回退）→ 快递鸟下单（真实 / mock 回退）拿到
          tracking_no / provider → 落库 FulfillmentOrder（status=SHIPPED，填 shipped_at）
          → 写审计 SHIP → 状态迁移（guard: fulfillment_agent）→ commit。

    若线索当前非 SIGNED，transition 的 guard 会拒绝，本函数回滚未提交事务并将 message
    透传给调用方（ok=False，不落库发货单）。
    """
    lead = session.get(models.Lead, lead_id)
    if lead is None:
        return {"ok": False, "reason": "线索不存在"}

    # 1) WMS 出库
    wms_receipt = wms.create_outbound(lead, sku, qty)

    # 2) 快递鸟物流下单（收件信息可空，空则回退 lead 自身信息）
    logistics_receipt = kdniao_logistics.create_order(
        receiver_name=receiver_name or lead.name,
        receiver_phone=receiver_phone or (lead.phone or ""),
        receiver_address=receiver_address or lead.company,
        sku=sku,
        qty=qty,
        lead=lead,
    )
    tracking_no = logistics_receipt.get("tracking_no", "")
    logistics_provider = logistics_receipt.get("provider", "mock")

    # 3) 关联该 lead 最近一条合同（若有）
    contract = (
        session.execute(
            select(models.Contract)
            .where(models.Contract.lead_id == lead_id)
            .order_by(models.Contract.id.desc())
        ).scalars().first()
    )

    order = models.FulfillmentOrder(
        lead_id=lead_id,
        contract_id=contract.id if contract is not None else None,
        sku=sku,
        qty=qty,
        receiver_name=receiver_name,
        receiver_phone=receiver_phone,
        receiver_address=receiver_address,
        tracking_no=tracking_no,
        logistics_provider=logistics_provider,
        status="SHIPPED",
        shipped_at=datetime.now(),
    )
    session.add(order)

    session.add(models.AuditLog(
        event_type="SHIP", lead_id=lead_id, agent="fulfillment_agent",
        detail=(
            f"sku={sku}; qty={qty}; tracking_no={tracking_no}; "
            f"wms={wms_receipt.get('provider')}; provider={logistics_provider}"
        ),
    ))

    # 4) 状态迁移（guard: fulfillment_agent；SIGNED → SHIPPED）
    result = transition(session, lead_id, LeadState.SHIPPED, agent="fulfillment_agent", audit=True)
    if not result.ok:
        session.rollback()
        logger.warning("[FULFILLMENT] 发货状态迁移被拒绝：%s", result.message)
        return {"ok": False, "message": result.message, "reason": result.message}

    session.commit()
    return {
        "ok": True,
        "message": "发货成功",
        "tracking_no": tracking_no,
        "logistics_provider": logistics_provider,
    }
