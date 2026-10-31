"""Pydantic v2 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from typing import Any

from app import models
from app.state_machine import LeadState


class HealthOut(BaseModel):
    status: str


class GenericOut(BaseModel):
    ok: bool
    detail: str = ""


class LeadOut(BaseModel):
    id: int
    unified_key: str
    name: str
    company: str
    credit_code: str | None = None
    phone: str | None = None
    source: str
    tier: str | None = None
    score: int | None = None
    pilp_consent: bool
    state: str
    created_at: datetime

    @classmethod
    def from_model(cls, lead: "models.Lead") -> "LeadOut":
        state = lead.state.state if lead.state else LeadState.NEW.value
        return cls(
            id=lead.id,
            unified_key=lead.unified_key,
            name=lead.name,
            company=lead.company,
            credit_code=lead.credit_code,
            phone=lead.phone,
            source=lead.source,
            tier=lead.tier,
            score=lead.score,
            pilp_consent=lead.pilp_consent,
            state=state,
            created_at=lead.created_at,
        )


class AuditOut(BaseModel):
    id: int
    event_type: str
    lead_id: int | None
    agent: str | None
    detail: str
    created_at: datetime

    @classmethod
    def from_model(cls, a: "models.AuditLog") -> "AuditOut":
        return cls(
            id=a.id,
            event_type=a.event_type,
            lead_id=a.lead_id,
            agent=a.agent,
            detail=a.detail,
            created_at=a.created_at,
        )


class SettingsOut(BaseModel):
    """全量系统配置（采集 / 评分 / 合规 三段）。"""
    collection: dict[str, Any]
    scoring: dict[str, Any]
    compliance: dict[str, Any]


class SettingsUpdate(BaseModel):
    """部分更新系统配置：仅传需要改的段（其余保持默认/库内值）。"""
    collection: dict[str, Any] | None = None
    scoring: dict[str, Any] | None = None
    compliance: dict[str, Any] | None = None


class ContractOut(BaseModel):
    id: int
    lead_id: int
    contract_no: str
    signer_name: str | None = None
    signer_phone: str | None = None
    contract_url: str
    provider: str
    status: str
    created_at: datetime
    signed_at: datetime | None = None

    @classmethod
    def from_model(cls, c: "models.Contract") -> "ContractOut":
        return cls(
            id=c.id,
            lead_id=c.lead_id,
            contract_no=c.contract_no,
            signer_name=c.signer_name,
            signer_phone=c.signer_phone,
            contract_url=c.contract_url,
            provider=c.provider,
            status=c.status,
            created_at=c.created_at,
            signed_at=c.signed_at,
        )


class FulfillmentOrderOut(BaseModel):
    id: int
    lead_id: int
    contract_id: int | None = None
    sku: str
    qty: int
    receiver_name: str | None = None
    receiver_phone: str | None = None
    receiver_address: str | None = None
    tracking_no: str | None = None
    logistics_provider: str
    status: str
    created_at: datetime
    shipped_at: datetime | None = None

    @classmethod
    def from_model(cls, o: "models.FulfillmentOrder") -> "FulfillmentOrderOut":
        return cls(
            id=o.id,
            lead_id=o.lead_id,
            contract_id=o.contract_id,
            sku=o.sku,
            qty=o.qty,
            receiver_name=o.receiver_name,
            receiver_phone=o.receiver_phone,
            receiver_address=o.receiver_address,
            tracking_no=o.tracking_no,
            logistics_provider=o.logistics_provider,
            status=o.status,
            created_at=o.created_at,
            shipped_at=o.shipped_at,
        )


class SignRequest(BaseModel):
    """POST /leads/{lead_id}/sign 请求体。"""

    signer_name: str = ""
    signer_phone: str = ""


class ShipRequest(BaseModel):
    """POST /leads/{lead_id}/ship 请求体。"""

    sku: str = "DEFAULT"
    qty: int = 1
    receiver_name: str = ""
    receiver_phone: str = ""
    receiver_address: str = ""
