"""Mock 外部通道。

MVP 阶段全部为本地 mock（仅打印/记日志，不调真实阿里云/运营商/电子签/WMS）。
预留真实接入点：方法签名保持，未来替换为 http 调用即可。
"""
from __future__ import annotations

import logging

from app import models

logger = logging.getLogger("supply.mock_channels")


def mock_sms_send(lead: "models.Lead", content: str) -> dict:
    """模拟短信下发（阿里云短信占位）。返回通道回执。"""
    receipt = {
        "channel": "SMS",
        "lead_id": lead.id,
        "phone": lead.phone,
        "content": content,
        "status": "MOCK_SENT",
    }
    logger.info("[MOCK SMS] -> %s : %s", lead.phone, content)
    print(f"[MOCK SMS] 向 {lead.phone} 发送：{content}")
    return receipt


def mock_outbound(lead: "models.Lead", content: str) -> dict:
    """模拟外呼（运营商/AI 外呼占位）。"""
    receipt = {
        "channel": "OUTBOUND",
        "lead_id": lead.id,
        "phone": lead.phone,
        "content": content,
        "status": "MOCK_CALLED",
    }
    logger.info("[MOCK OUTBOUND] -> %s : %s", lead.phone, content)
    print(f"[MOCK OUTBOUND] 拨打 {lead.phone}：{content}")
    return receipt


# ---- 以下为后续环节占位（fulfillment_agent 使用） ----


def mock_e_sign(lead: "models.Lead", contract_url: str) -> dict:
    """模拟电子签约（未来接 e签宝/法大大）。"""
    logger.info("[MOCK E-SIGN] lead=%s contract=%s", lead.id, contract_url)
    print(f"[MOCK E-SIGN] 线索 {lead.id} 签约：{contract_url}")
    return {"channel": "E_SIGN", "lead_id": lead.id, "status": "MOCK_SIGNED"}


def mock_wms(lead: "models.Lead", sku: str, qty: int) -> dict:
    """模拟 WMS 发货（未来接仓储系统）。"""
    logger.info("[MOCK WMS] lead=%s sku=%s qty=%s", lead.id, sku, qty)
    print(f"[MOCK WMS] 线索 {lead.id} 出库：sku={sku} qty={qty}")
    return {"channel": "WMS", "lead_id": lead.id, "status": "MOCK_DISPATCHED"}


def mock_logistics(lead: "models.Lead", tracking_no: str) -> dict:
    """模拟物流（未来接快递 100/顺丰）。"""
    logger.info("[MOCK LOGISTICS] lead=%s tracking=%s", lead.id, tracking_no)
    print(f"[MOCK LOGISTICS] 线索 {lead.id} 物流单号：{tracking_no}")
    return {"channel": "LOGISTICS", "lead_id": lead.id, "status": "MOCK_SHIPPED"}
