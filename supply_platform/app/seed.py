"""种子数据：写入示例商户 + 合规名单，便于演示与测试。"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.agents import data_agent

logger = logging.getLogger("supply.seed")


def seed(session: Session) -> dict:
    """写入种子数据。幂等：已存在则跳过。"""
    # 1) 商户线索（通过 data_agent 采集入库，统一路径）
    existing = session.execute(select(models.Lead)).scalars().all()
    if existing:
        leads = existing
    else:
        leads = data_agent.collect(session)

    # 2) 合规名单（演示拦截）
    # 退订：深圳前海数据服务 (13800000004)
    # 谢绝来电：上海浦江贸易 (13800000002)
    _ensure_compliance(session, "OPT_OUT", "13800000004", "用户回复退订")
    _ensure_compliance(session, "DO_NOT_CALL", "13800000002", "登记的谢绝来电")

    session.commit()
    return {"leads": len(leads), "compliance_entries": 2}


def _ensure_compliance(session: Session, ctype: str, key: str, reason: str) -> None:
    exists = session.execute(
        select(models.ComplianceList).where(
            models.ComplianceList.type == ctype, models.ComplianceList.key == key
        )
    ).scalars().first()
    if exists is None:
        session.add(models.ComplianceList(type=ctype, key=key, reason=reason))
