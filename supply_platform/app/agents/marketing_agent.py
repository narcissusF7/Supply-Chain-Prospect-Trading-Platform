"""Marketing Agent（营销触达智能体）。

职责边界（独立模块，体现"隔离会话"）：
- outreach: 对 SCORED 线索执行触达。
  流程：compliance.check → (不通过则审计+阻断) → mock_sms_send →
        写 ContactTask(幂等 dedup_key) → 审计 → 状态迁移 SCORED→CONTACTED

扩展点：
- 真实短信通道：替换 mock_sms_send 为阿里云 SMS SDK 调用。
- 编排：未来由 LangGraph 节点触发，而非确定性函数。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.channels import aliyun_sms
from app.compliance import ComplianceGuard
from app.mock_channels import mock_outbound
from app.state_machine import LeadState, transition

logger = logging.getLogger("supply.marketing_agent")


def _dedup_key(lead_id: int, channel: str, intent: str = "initial") -> str:
    return f"{lead_id}:{channel}:{intent}"


def outreach(
    session: Session,
    lead_id: int,
    channel: str = "SMS",
    content: str | None = None,
) -> dict:
    """对单一线索触达。返回执行结果摘要。

    触达前必过合规中间件；发送后写触达任务与审计，并迁移状态。
    """
    lead = session.get(models.Lead, lead_id)
    if lead is None:
        return {"ok": False, "reason": "线索不存在"}

    # 1) 合规守护（横切）：强制校验
    allow, reason = ComplianceGuard.check(lead, channel=channel, session=session)
    # 写合规审计（无论通过与否均留痕）
    session.add(models.AuditLog(
        event_type="COMPLIANCE",
        lead_id=lead_id,
        agent="marketing_agent",
        detail=f"allow={allow}; {reason}",
    ))
    if not allow:
        # 不通过即阻断
        session.commit()
        return {"ok": False, "blocked_by_compliance": True, "reason": reason}

    # 2) 幂等防重复触达：dedup_key 唯一约束
    dedup = _dedup_key(lead_id, channel)
    existing_task = session.execute(
        select(models.ContactTask).where(models.ContactTask.dedup_key == dedup)
    ).scalars().first()
    if existing_task is not None:
        return {
            "ok": True, "idempotent": True, "reason": "已触达，幂等跳过",
            "contact_task_id": existing_task.id,
        }

    # 3) 调用短信通道：SMS 走真实阿里云通道（带回退 mock）；OUTBOUND 保留 mock 外呼
    text = content or (
        f"【供应平台】尊敬的{lead.company}，您好！我们为您匹配了专属供应链方案，"
        f"回复 R 了解更多。"
    )
    if channel == "OUTBOUND":
        receipt = mock_outbound(lead, text)
    else:
        receipt = aliyun_sms.send_sms(lead, text, session=session)

    # 4) 写触达任务
    task = models.ContactTask(
        lead_id=lead_id, channel=channel, content=text, dedup_key=dedup, status="SENT",
    )
    session.add(task)

    # 5) 审计
    session.add(models.AuditLog(
        event_type="OUTREACH", lead_id=lead_id, agent="marketing_agent",
        detail=f"channel={channel}; receipt={receipt['status']}",
    ))

    # 6) 状态迁移 SCORED → CONTACTED（guard: marketing_agent）
    result = transition(session, lead_id, LeadState.CONTACTED, agent="marketing_agent", audit=True)
    if not result.ok:
        # 迁移失败也记录（如非 SCORED 状态）
        session.add(models.AuditLog(
            event_type="STATE_CHANGE_FAILED", lead_id=lead_id, agent="marketing_agent",
            detail=result.message,
        ))

    session.commit()
    return {
        "ok": True,
        "lead_id": lead_id,
        "channel": channel,
        "contact_task_id": task.id,
        "state_result": result.message,
    }
