"""SQLAlchemy ORM 模型定义。

实体清单：
- Lead           商户线索主表（含评分相关原始字段 region/employees）
- LeadState      线索状态机单一事实源（与 Lead 一对一）
- ComplianceList 合规名单（退订 / 谢绝来电）
- ContactTask    触达任务（短信/外呼），含 dedup_key 幂等键
- AuditLog       审计日志
- Tag / LeadTag  标签与线索标签多对多
- Contract           电子签约合同（法大大真实通道 / mock 回退）
- FulfillmentOrder   履约发货单（WMS 出库 + 快递鸟物流，mock 回退）
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Lead(Base):
    """商户线索。统一主键为 unified_key（统一社会信用代码优先，否则手机号）。"""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    unified_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
        comment="去重主键：统一社会信用代码或手机号",
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="联系人姓名")
    company: Mapped[str] = mapped_column(String(256), nullable=False, comment="公司名称")
    credit_code: Mapped[str | None] = mapped_column(
        String(32), index=True, nullable=True, comment="统一社会信用代码",
    )
    phone: Mapped[str | None] = mapped_column(
        String(32), index=True, nullable=True, comment="手机号",
    )
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="seed", comment="数据来源",
    )
    # 评分相关原始字段（采集时落库，供 /score 阶段确定性重算）
    region: Mapped[str] = mapped_column(String(32), nullable=False, default="other", comment="区域")
    employees: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="员工规模")
    tier: Mapped[str | None] = mapped_column(String(8), nullable=True, comment="分层 A/B/C")
    score: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="评分")
    pilp_consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="PIPL 同意标志",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    state: Mapped["LeadState"] = relationship(
        "LeadState", back_populates="lead", uselist=False, cascade="all, delete-orphan",
    )
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", secondary="lead_tags", back_populates="leads",
    )


class LeadState(Base):
    """线索状态：状态机的单一事实源。"""

    __tablename__ = "lead_states"
    __table_args__ = (UniqueConstraint("lead_id", name="uq_lead_state"),)

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True,
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="NEW")
    current_agent: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="当前状态归属 agent",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    lead: Mapped["Lead"] = relationship("Lead", back_populates="state")


class ComplianceList(Base):
    """合规名单。type 区分 退订(OPT_OUT) / 谢绝来电(DO_NOT_CALL)。"""

    __tablename__ = "compliance_lists"
    __table_args__ = (UniqueConstraint("type", "key", name="uq_compliance_type_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="OPT_OUT / DO_NOT_CALL",
    )
    key: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="匹配键：phone 或 credit_code",
    )
    reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )


class ContactTask(Base):
    """触达任务（短信/外呼）。dedup_key 用于幂等防重复触达。"""

    __tablename__ = "contact_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False, comment="SMS / OUTBOUND")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    dedup_key: Mapped[str] = mapped_column(
        String(128), unique=True, index=True, nullable=False,
        comment="幂等键：lead_id+channel+意图",
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SENT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )


class AuditLog(Base):
    """审计日志：所有触达/合规校验/状态变更留痕。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True,
        comment="OUTREACH/COMPLIANCE/STATE_CHANGE/...",
    )
    lead_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    agent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True,
    )


class Tag(Base):
    """标签。"""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    leads: Mapped[list["Lead"]] = relationship(
        "Lead", secondary="lead_tags", back_populates="tags",
    )


class LeadTag(Base):
    """线索-标签关联表。"""

    __tablename__ = "lead_tags"
    __table_args__ = (UniqueConstraint("lead_id", "tag_id", name="uq_lead_tag"),)

    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True,
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True,
    )


class SystemConfig(Base):
    """系统配置键值表。

    按 section 名（collection / scoring / compliance）存整段 JSON 配置。
    未写入时由 app.config_store.DEFAULT_CONFIG 提供默认值；写入后以库内值为准。
    """

    __tablename__ = "system_configs"

    key: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="section 名",
    )
    value: Mapped[str] = mapped_column(
        Text, nullable=False, comment="该段配置的 JSON 字符串",
    )
    description: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="配置段说明",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class Contract(Base):
    """电子签约合同（法大大真实通道 / mock 回退）。

    一条线索在 INTERESTED → SIGNED 迁移时由 fulfillment_agent 落库一条合同，
    demo 中签约成功即视为已签（status=SIGNED，填 signed_at）。
    """

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False,
        comment="关联线索",
    )
    contract_no: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False,
        comment="合同编号，如 CT{datetime}{lead_id}",
    )
    signer_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="签约人姓名",
    )
    signer_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="签约人手机号",
    )
    contract_url: Mapped[str] = mapped_column(
        Text, nullable=False, comment="合同文件 / 签署链接",
    )
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="mock", comment="签约通道：fadada / mock",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PENDING", comment="PENDING / SIGNED",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FulfillmentOrder(Base):
    """履约发货单（WMS 出库 + 快递鸟物流，mock 回退）。

    一条线索在 SIGNED → SHIPPED 迁移时由 fulfillment_agent 落库一条发货单，
    记录物流单号、物流商与收件信息；可关联对应 Contract。
    """

    __tablename__ = "fulfillment_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=False,
        comment="关联线索",
    )
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("contracts.id", ondelete="SET NULL"), index=True, nullable=True,
        comment="关联合同（可空）",
    )
    sku: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="商品 SKU",
    )
    qty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="数量",
    )
    receiver_name: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="收件人姓名",
    )
    receiver_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="收件人手机号",
    )
    receiver_address: Mapped[str | None] = mapped_column(
        String(256), nullable=True, comment="收件地址",
    )
    tracking_no: Mapped[str | None] = mapped_column(
        String(64), index=True, nullable=True, comment="物流单号",
    )
    logistics_provider: Mapped[str] = mapped_column(
        String(32), nullable=False, default="mock", comment="物流商：kdniao / mock",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="CREATED",
        comment="CREATED / SHIPPED / DELIVERED",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
    )
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
