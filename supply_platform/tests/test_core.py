"""核心逻辑测试：状态机 / 合规拦截 / 去重 / 频次上限 / 触达幂等。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app import models
from app.agents import data_agent, marketing_agent
from app.compliance import ComplianceGuard
from app.db import SessionLocal
from app.state_machine import LeadState, transition


def _make_lead(session, **kwargs) -> models.Lead:
    defaults = dict(
        unified_key="TESTKEY1", name="测试", company="测试公司",
        credit_code="C1", phone="13900000001", source="test",
        region="beijing", employees=200, pilp_consent=True,
    )
    defaults.update(kwargs)
    lead = models.Lead(**defaults)
    session.add(lead)
    session.flush()
    session.add(models.LeadState(lead_id=lead.id, state=LeadState.NEW.value))
    session.commit()
    return lead


# ---------------- 状态机 ----------------


def test_state_machine_illegal_transition(session):
    lead = _make_lead(session, unified_key="K1")
    # NEW -> CONTACTED 非法
    r = transition(session, lead.id, LeadState.CONTACTED, agent="marketing_agent")
    assert r.ok is False
    assert "非法迁移" in r.message


def test_state_machine_guard(session):
    lead = _make_lead(session, unified_key="K2")
    # 正确 agent 应为 data_agent，错误 agent 被 guard 拒绝
    r = transition(session, lead.id, LeadState.SCORED, agent="marketing_agent")
    assert r.ok is False
    assert "guard" in r.message
    r2 = transition(session, lead.id, LeadState.SCORED, agent="data_agent")
    assert r2.ok is True


def test_state_machine_idempotent(session):
    lead = _make_lead(session, unified_key="K3")
    r1 = transition(session, lead.id, LeadState.SCORED, agent="data_agent")
    assert r1.ok
    r2 = transition(session, lead.id, LeadState.SCORED, agent="data_agent")
    assert r2.ok  # 已是目标状态，幂等
    assert "幂等" in r2.message


# ---------------- 合规拦截 ----------------


def test_compliance_blocks_no_consent(session):
    lead = _make_lead(session, unified_key="K4", pilp_consent=False)
    allow, reason = ComplianceGuard.check(lead, session=session)
    assert allow is False
    assert "PIPL" in reason


def test_compliance_blocks_opt_out(session):
    lead = _make_lead(session, unified_key="K5", phone="13900000099")
    session.add(models.ComplianceList(type="OPT_OUT", key="13900000099", reason="test"))
    session.commit()
    allow, reason = ComplianceGuard.check(lead, session=session)
    assert allow is False
    assert "退订" in reason


def test_compliance_blocks_do_not_call(session):
    lead = _make_lead(session, unified_key="K6", phone="13900000098")
    session.add(models.ComplianceList(type="DO_NOT_CALL", key="13900000098", reason="test"))
    session.commit()
    allow, reason = ComplianceGuard.check(lead, session=session)
    assert allow is False
    assert "谢绝来电" in reason


def test_compliance_blocks_off_hours(session, monkeypatch):
    lead = _make_lead(session, unified_key="K7", phone="13900000097")
    # 模拟凌晨 3 点外呼
    class FakeDT:
        @staticmethod
        def now():
            return datetime(2024, 1, 1, 3, 0, 0)

    monkeypatch.setattr(ComplianceGuard, "_now", FakeDT.now)
    allow, reason = ComplianceGuard.check(lead, channel="OUTBOUND", session=session)
    assert allow is False
    assert "时段" in reason


def test_compliance_blocks_frequency_cap(session):
    lead = _make_lead(session, unified_key="K8", phone="13900000096")
    for i in range(3):
        session.add(models.ContactTask(
            lead_id=lead.id, channel="SMS", content="x", dedup_key=f"K8:SMS:{i}",
        ))
    session.commit()
    allow, reason = ComplianceGuard.check(lead, session=session)
    assert allow is False
    assert "上限" in reason


def test_compliance_pass(session):
    lead = _make_lead(session, unified_key="K9", phone="13900000095")
    allow, reason = ComplianceGuard.check(lead, session=session)
    assert allow is True


# ---------------- 去重合并 ----------------


def test_dedup_merge(session):
    raw = {
        "name": "张三", "company": "A公司", "credit_code": "CARDUP1",
        "phone": "13700000001", "region": "beijing", "employees": 100,
        "pilp_consent": True, "source": "test",
    }
    data_agent.ingest(session, [raw])
    # 再次 ingest 同主键 → 仍只有 1 条
    data_agent.ingest(session, [raw])
    cnt = session.execute(
        select(func.count(models.Lead.id)).where(models.Lead.unified_key == "CARDUP1")
    ).scalar_one()
    assert cnt == 1


# ---------------- 触达幂等 ----------------


def test_outreach_idempotent(session):
    lead = _make_lead(session, unified_key="K10", phone="13900000094", pilp_consent=True)
    transition(session, lead.id, LeadState.SCORED, agent="data_agent")
    session.commit()
    r1 = marketing_agent.outreach(session, lead.id)
    assert r1["ok"] is True
    r2 = marketing_agent.outreach(session, lead.id)
    assert r2.get("idempotent") is True


def test_outreach_compliance_block(session):
    lead = _make_lead(session, unified_key="K11", phone="13900000093", pilp_consent=False)
    transition(session, lead.id, LeadState.SCORED, agent="data_agent")
    session.commit()
    r = marketing_agent.outreach(session, lead.id)
    assert r["ok"] is False
    assert r["blocked_by_compliance"] is True
