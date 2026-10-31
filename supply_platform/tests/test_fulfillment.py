"""签约履约（fulfillment_agent + 真实通道回退 + REST 端点）测试。

不破坏既有 16 个用例；本节验证：
1) sign 在无凭据时走 mock、生成 Contract 记录、且状态机从 INTERESTED→SIGNED 成功；
2) sign 对状态非 INTERESTED 的 lead 返回 ok=False（guard 拦截）；
3) ship 在无凭据时走 mock、生成 FulfillmentOrder 且有 tracking_no、状态机 SIGNED→SHIPPED 成功；
4) ship 对状态非 SIGNED 的 lead 返回 ok=False；
5) 新 REST 端点冒烟（FastAPI TestClient，若可用）；
6) listContracts / listOrders 返回结构与模型一致。
"""
from __future__ import annotations

from sqlalchemy import func, select

from app import models
from app.agents import fulfillment_agent
from app.channels import fadada_esign, kdniao_logistics, wms
from app.state_machine import LeadState


def _make_lead(session, state: LeadState = LeadState.NEW, **kwargs) -> models.Lead:
    defaults = dict(
        unified_key="FULFILL1", name="履约测试", company="履约公司",
        credit_code="FC1", phone="13922220001", source="test",
        region="beijing", employees=200, pilp_consent=True,
    )
    defaults.update(kwargs)
    lead = models.Lead(**defaults)
    session.add(lead)
    session.flush()
    session.add(models.LeadState(lead_id=lead.id, state=state.value))
    session.commit()
    return lead


def _clear_credentials(monkeypatch):
    """清除所有真实通道的环境变量，确保走 mock 回退。"""
    for var in (
        "FADADA_APP_ID", "FADADA_APP_SECRET", "FADADA_HOST",
        "KDNIAO_APP_KEY", "KDNIAO_APP_SECRET", "KDNIAO_EBUSINESS_ID", "KDNIAO_HOST",
        "WMS_HOST", "WMS_TOKEN",
    ):
        monkeypatch.delenv(var, raising=False)


# ---------------- sign ----------------


def test_sign_mock_and_contract_created(session, monkeypatch):
    """无凭据时 sign 走 mock、生成 Contract、状态机 INTERESTED→SIGNED 成功。"""
    _clear_credentials(monkeypatch)
    lead = _make_lead(session, state=LeadState.INTERESTED, unified_key="SIGN_MOCK")

    res = fulfillment_agent.sign(session, lead.id, signer_name="张三", signer_phone="13900000001")

    assert res["ok"] is True
    assert res["provider"] == "mock"
    assert res["contract_no"].startswith("CT")
    assert res["contract_url"].startswith("https://mock/contract/")

    # 合同数 = 1
    cnt = session.execute(
        select(func.count(models.Contract.id)).where(models.Contract.lead_id == lead.id)
    ).scalar_one()
    assert cnt == 1

    # 状态机推进到 SIGNED
    final = session.get(models.LeadState, lead.id)
    assert final.state == LeadState.SIGNED.value


def test_sign_guard_rejects_non_interested(session, monkeypatch):
    """状态非 INTERESTED 时 sign 返回 ok=False（guard 拦截，不落库合同）。"""
    _clear_credentials(monkeypatch)
    # 当前为 NEW（非 INTERESTED），迁移会被 guard 拒绝
    lead = _make_lead(session, state=LeadState.NEW, unified_key="SIGN_GUARD")

    res = fulfillment_agent.sign(session, lead.id)

    # NEW 不是 INTERESTED，迁移被状态机拒绝（非法迁移 / guard），ok=False 且不落库
    assert res["ok"] is False
    assert ("非法迁移" in res.get("message", "")) or ("guard" in res.get("message", ""))

    # 不应落库合同
    cnt = session.execute(
        select(func.count(models.Contract.id)).where(models.Contract.lead_id == lead.id)
    ).scalar_one()
    assert cnt == 0
    final = session.get(models.LeadState, lead.id)
    assert final.state == LeadState.NEW.value


# ---------------- ship ----------------


def test_ship_mock_and_order_created(session, monkeypatch):
    """无凭据时 ship 走 mock、生成 FulfillmentOrder 且有 tracking_no、状态机 SIGNED→SHIPPED 成功。"""
    _clear_credentials(monkeypatch)
    lead = _make_lead(session, state=LeadState.SIGNED, unified_key="SHIP_MOCK")

    res = fulfillment_agent.ship(
        session, lead.id, sku="SKU-A", qty=2,
        receiver_name="李四", receiver_phone="13900000002", receiver_address="北京市",
    )

    assert res["ok"] is True
    assert res["logistics_provider"] == "mock"
    assert res["tracking_no"]  # 非空

    # 履约单数 = 1 且带 tracking_no
    order = session.execute(
        select(models.FulfillmentOrder)
        .where(models.FulfillmentOrder.lead_id == lead.id)
        .order_by(models.FulfillmentOrder.id.desc())
    ).scalars().first()
    assert order is not None
    assert order.tracking_no == res["tracking_no"]
    assert order.status == "SHIPPED"

    # 状态机推进到 SHIPPED
    final = session.get(models.LeadState, lead.id)
    assert final.state == LeadState.SHIPPED.value


def test_ship_guard_rejects_non_signed(session, monkeypatch):
    """状态非 SIGNED 时 ship 返回 ok=False（guard 拦截，不落库发货单）。"""
    _clear_credentials(monkeypatch)
    # 当前为 INTERESTED（非 SIGNED），迁移会被 guard 拒绝
    lead = _make_lead(session, state=LeadState.INTERESTED, unified_key="SHIP_GUARD")

    res = fulfillment_agent.ship(session, lead.id)

    # INTERESTED 不是 SIGNED，迁移被状态机拒绝（非法迁移 / guard），ok=False 且不落库
    assert res["ok"] is False
    assert ("非法迁移" in res.get("message", "")) or ("guard" in res.get("message", ""))

    cnt = session.execute(
        select(func.count(models.FulfillmentOrder.id)).where(models.FulfillmentOrder.lead_id == lead.id)
    ).scalar_one()
    assert cnt == 0
    final = session.get(models.LeadState, lead.id)
    assert final.state == LeadState.INTERESTED.value


# ---------------- 通道回退（无凭据） ----------------


def test_channels_fallback_without_credentials(session, monkeypatch):
    """无凭据时三个新通道均回退 mock。"""
    _clear_credentials(monkeypatch)
    lead = _make_lead(session, state=LeadState.INTERESTED, unified_key="CH_FALLBACK")

    c = fadada_esign.send_contract(lead, signer_name="王五")
    assert c["provider"] == "mock"
    assert c["status"] == "SIGNED"

    o = kdniao_logistics.create_order("收", "139", "地址", "SKU", 1, lead)
    assert o["provider"] == "mock"
    assert o["tracking_no"]

    t = kdniao_logistics.query_tracking("KDMOCK123")
    assert t["provider"] == "mock"
    assert isinstance(t["traces"], list)

    w = wms.create_outbound(lead, "SKU", 1)
    assert w["provider"] == "mock"


# ---------------- REST 端点冒烟（TestClient 可选） ----------------


def _get_client():
    try:
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app)
    except Exception:  # pragma: no cover - 取决于运行环境是否安装 TestClient/httpx
        return None


def test_main_imports_and_routes():
    """app.main 可正常 import，且新端点已注册（即便不跑 TestClient 也验证不报错）。"""
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/leads/{lead_id}/sign" in paths
    assert "/api/v1/leads/{lead_id}/ship" in paths
    assert "/api/v1/contracts" in paths
    assert "/api/v1/orders" in paths
    assert "/api/v1/leads/{lead_id}/tracking" in paths


def test_endpoint_smoke_sign_and_list(session, monkeypatch):
    """通过 TestClient 冒烟验证 /sign 与 /contracts、/orders（若 TestClient 可用）。"""
    client = _get_client()
    if client is None:
        import pytest

        pytest.skip("TestClient/httpx 不可用，跳过端点冒烟")
    _clear_credentials(monkeypatch)

    # 准备一个 INTERESTED 线索（写入共享测试库）
    lead = _make_lead(session, state=LeadState.INTERESTED, unified_key="EP_SIGN")
    session.commit()

    # 签约
    r = client.post(
        f"/api/v1/leads/{lead.id}/sign",
        json={"signer_name": "赵六", "signer_phone": "13900000006"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    # 列表结构与模型一致
    cr = client.get("/api/v1/contracts")
    assert cr.status_code == 200
    contracts = cr.json()
    assert isinstance(contracts, list) and len(contracts) >= 1
    assert "contract_no" in contracts[0] and "provider" in contracts[0]

    # 发货
    r2 = client.post(
        f"/api/v1/leads/{lead.id}/ship",
        json={"sku": "SKU-EP", "qty": 1, "receiver_name": "赵六", "receiver_phone": "13900000006", "receiver_address": "上海"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["ok"] is True

    orr = client.get("/api/v1/orders")
    assert orr.status_code == 200
    orders = orr.json()
    assert isinstance(orders, list) and len(orders) >= 1
    assert "tracking_no" in orders[0] and "logistics_provider" in orders[0]

    # 物流轨迹（无真实凭据 → mock 轨迹）
    tr = client.get(f"/api/v1/leads/{lead.id}/tracking")
    assert tr.status_code == 200
    assert tr.json()["provider"] in ("mock", "kdniao")


def test_endpoint_sign_guard_400(session, monkeypatch):
    """对非 INTERESTED 线索签约应返回 400。"""
    client = _get_client()
    if client is None:
        import pytest

        pytest.skip("TestClient/httpx 不可用，跳过端点冒烟")
    _clear_credentials(monkeypatch)

    lead = _make_lead(session, state=LeadState.NEW, unified_key="EP_GUARD")
    session.commit()

    r = client.post(f"/api/v1/leads/{lead.id}/sign", json={})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert ("非法迁移" in detail) or ("guard" in detail)
