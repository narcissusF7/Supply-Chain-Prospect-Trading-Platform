"""阿里云短信通道（回退/mock）与 orchestrator 派活相关测试。

不破坏既有 12 个核心用例；本节新增验证：
1) 无阿里云凭据时回退 mock 仍触达成功、且不调用真实发送；
2) 配置凭据时通道选择正确（注入 fake client 避免真实发信）；
3) 合规不通过时绝不调用短信接口；
4) orchestrator.dispatch 在未启用 langgraph 时回退确定性实现仍可跑通。
"""
from __future__ import annotations

from sqlalchemy import func, select

from app import models
from app.channels import aliyun_sms
from app.state_machine import LeadState


def _make_lead(session, **kwargs) -> models.Lead:
    defaults = dict(
        unified_key="CH1", name="渠道测试", company="渠道公司",
        credit_code="CC1", phone="13911112222", source="test",
        region="beijing", employees=200, pilp_consent=True,
    )
    defaults.update(kwargs)
    lead = models.Lead(**defaults)
    session.add(lead)
    session.flush()
    session.add(models.LeadState(lead_id=lead.id, state=LeadState.SCORED.value))
    session.commit()
    return lead


# ---------------- 阿里云短信通道回退 ----------------


def test_sms_fallback_mock_without_credentials(session, monkeypatch):
    """无阿里云凭据时回退 mock，触达仍成功且未调用真实发送实现。"""
    for var in (
        "ALIYUN_SMS_ACCESS_KEY_ID", "ALIYUN_SMS_ACCESS_KEY_SECRET",
        "ALIYUN_SMS_SIGN_NAME", "ALIYUN_SMS_TEMPLATE_CODE",
    ):
        monkeypatch.delenv(var, raising=False)

    called = {"sdk": False, "rpc": False}
    monkeypatch.setattr(
        aliyun_sms, "_sdk_send_sms",
        lambda *a, **k: called.__setitem__("sdk", True) or {},
    )
    monkeypatch.setattr(
        aliyun_sms, "_rpc_send_sms",
        lambda *a, **k: called.__setitem__("rpc", True) or {},
    )

    lead = _make_lead(session, unified_key="CH_NOENV", phone="13911110001")
    receipt = aliyun_sms.send_sms(lead, "测试内容", session=session)

    assert receipt["status"] == "MOCK_SENT"
    assert called["sdk"] is False
    assert called["rpc"] is False


def test_sms_channel_selects_real_with_credentials(session, monkeypatch):
    """配置凭据时选择真实通道（注入 fake client 避免真实发信）。"""
    monkeypatch.setenv("ALIYUN_SMS_ACCESS_KEY_ID", "fake-id")
    monkeypatch.setenv("ALIYUN_SMS_ACCESS_KEY_SECRET", "fake-secret")
    monkeypatch.setenv("ALIYUN_SMS_SIGN_NAME", "测试签名")
    monkeypatch.setenv("ALIYUN_SMS_TEMPLATE_CODE", "SMS_000")

    fake = {"called": False}

    def fake_rpc(*args, **kwargs):
        fake["called"] = True
        return {"Code": "OK", "BizId": "123"}

    # 本环境无官方 SDK → 走 RPC 路径；注入 fake 避免联网
    monkeypatch.setattr(aliyun_sms, "_rpc_send_sms", fake_rpc)

    lead = _make_lead(session, unified_key="CH_REAL", phone="13911110002")
    receipt = aliyun_sms.send_sms(lead, "测试内容", session=session)

    assert receipt["provider"] == "aliyun"
    assert receipt["status"] == "SENT"
    assert receipt["sdk"] == "rpc_v1"
    assert fake["called"] is True


def test_sms_compliance_blocks_before_send(session, monkeypatch):
    """合规不通过（无 PIPL 同意）时绝不调用短信接口。"""
    monkeypatch.setenv("ALIYUN_SMS_ACCESS_KEY_ID", "fake-id")
    monkeypatch.setenv("ALIYUN_SMS_ACCESS_KEY_SECRET", "fake-secret")
    monkeypatch.setenv("ALIYUN_SMS_SIGN_NAME", "测试签名")
    monkeypatch.setenv("ALIYUN_SMS_TEMPLATE_CODE", "SMS_000")

    fake = {"called": False}
    monkeypatch.setattr(
        aliyun_sms, "_rpc_send_sms",
        lambda *a, **k: fake.__setitem__("called", True) or {"Code": "OK"},
    )

    lead = _make_lead(session, unified_key="CH_BLOCK", phone="13911110003", pilp_consent=False)
    receipt = aliyun_sms.send_sms(lead, "测试内容", session=session)

    assert receipt["status"] == "COMPLIANCE_BLOCKED"
    assert fake["called"] is False


# ---------------- orchestrator 派活回退 ----------------


def test_dispatch_deterministic_runs(session):
    """orchestrator.dispatch 在两种引擎下均可跑通（SCORED → 触达 → CONTACTED）。"""
    from app.orchestrator import dispatch

    lead = _make_lead(session, unified_key="DISP1", phone="13911110004")
    res = dispatch(session, lead.id)

    assert res["ok"] is True
    # 触达应已在库里产生一条 ContactTask
    cnt = session.execute(
        select(func.count(models.ContactTask.id)).where(models.ContactTask.lead_id == lead.id)
    ).scalar_one()
    assert cnt == 1
    # 状态应已推进到 CONTACTED
    final = session.get(models.LeadState, lead.id)
    assert final.state == LeadState.CONTACTED.value
