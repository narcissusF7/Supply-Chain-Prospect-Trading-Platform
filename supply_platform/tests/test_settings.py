"""系统设置（采集 / 评分 / 合规 可视化配置）测试。

验证：
1) 默认配置返回三段且数值与出厂默认一致；
2) 更新配置持久化且按段合并（其余默认值保留）；
3) 合规校验读取配置（频次上限改为 1 后，1 次历史触达即拦截）；
4) 评分读取配置（权重归零后总分相应下降）。
"""
from __future__ import annotations

from app import models
from app.agents import data_agent
from app.compliance import ComplianceGuard
from app.config_store import get_all, get_scoring_config, get_section, set_all
from app.state_machine import LeadState


def test_get_settings_returns_defaults(session):
    cfg = get_all(session)
    assert set(cfg.keys()) == {"collection", "scoring", "compliance"}
    assert cfg["compliance"]["frequency_cap"] == 3
    assert cfg["compliance"]["call_start_hour"] == 9
    assert cfg["scoring"]["tier_a_min"] == 80
    assert cfg["collection"]["source"] == "api_mock"


def test_update_settings_persists_and_merges(session):
    set_all(session, {"compliance": {"frequency_cap": 5}})
    session.commit()
    cfg = get_section(session, "compliance")
    assert cfg["frequency_cap"] == 5
    # 其余默认值保留（合并而非整体覆盖）
    assert cfg["call_start_hour"] == 9
    assert cfg["require_pilp_consent"] is True


def test_compliance_reads_config_cap(session):
    """频次上限改为 1 后，已有 1 次触达即被拦截。"""
    set_all(session, {"compliance": {"frequency_cap": 1, "require_pilp_consent": True}})
    session.commit()

    lead = models.Lead(
        unified_key="CFG_CAP1", name="配置测试", company="配置公司",
        credit_code="CC1", phone="13900001111", source="test",
        region="other", employees=0, pilp_consent=True,
    )
    session.add(lead)
    session.flush()
    session.add(models.LeadState(lead_id=lead.id, state=LeadState.CONTACTED.value))
    session.add(models.ContactTask(
        lead_id=lead.id, channel="SMS", content="x", dedup_key="CFG_CAP1:1",
    ))
    session.commit()

    allow, reason = ComplianceGuard.check(lead, session=session)
    assert allow is False
    assert "上限" in reason


def test_scoring_reads_config(session):
    """评分权重归零后，总分相应下降。"""
    n = {
        "name": "评分配置", "company": "评分公司", "credit_code": "CRD1",
        "phone": "13900002222", "region": "beijing", "employees": 150,
        "pilp_consent": True, "source": "test",
    }
    s_default, _ = data_agent.score(n, get_scoring_config(session))

    # 把两项权重归零：信用代码 30 -> 0，PIPL 20 -> 0
    set_all(session, {"scoring": {"credit_code_points": 0, "pilp_points": 0}})
    session.commit()

    s_custom, _ = data_agent.score(n, get_scoring_config(session))
    assert s_custom == s_default - 50
