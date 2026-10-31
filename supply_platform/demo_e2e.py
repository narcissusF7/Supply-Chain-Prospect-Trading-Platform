"""供应平台 MVP —— 端到端演示脚本。

通过真实 HTTP 调用后端（默认 http://127.0.0.1:8000），串起完整业务闭环：
  seed → collect → score → outreach(合规拦截) → intent → sign → ship → tracking
并演示「系统设置」配置可真实保存生效。

用法：
    python -m uvicorn app.main:app --port 8000   # 另开终端先起服务
    python demo_e2e.py
"""
from __future__ import annotations

import ast
import json
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
client = httpx.Client(base_url=BASE, trust_env=False, timeout=30)


def banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def jp(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def call(method: str, path: str, **kw):
    """发起请求，返回 (status_code, json_or_text)。"""
    r = getattr(client, method)(path, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def wait_health() -> bool:
    for _ in range(40):
        try:
            code, body = call("get", "/health")
            if code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    if not wait_health():
        print("!! 无法连接后端，请先启动 uvicorn")
        return 1

    # ---------- 0. 健康检查 ----------
    banner("0. 健康检查 / 服务就绪")
    code, body = call("get", "/health")
    print(f"GET /health -> {code} {body}")

    # ---------- 1. 种子数据 ----------
    banner("1. 注入种子数据（商户线索 + 合规名单）")
    code, body = call("post", "/seed")
    print(f"POST /seed -> {code}")
    print(f"  {body.get('detail')}")

    # ---------- 2. 采集（幂等验证） ----------
    banner("2. 采集（重复采集应被去重，新增 0）")
    code, body = call("post", "/collect")
    print(f"POST /collect -> {code}  {body.get('detail')}")

    # ---------- 3. 评分分层 ----------
    banner("3. 规则评分与分层（NEW → SCORED）")
    code, body = call("post", "/score")
    print(f"POST /score -> {code}  {body.get('detail')}")

    # ---------- 4. 查看已评分线索 ----------
    banner("4. 已评分线索（按分数从高到低）")
    code, leads = call("get", "/leads", params={"state": "SCORED"})
    leads_sorted = sorted(leads, key=lambda x: x.get("score") or 0, reverse=True)
    print(f"{'ID':>3}  {'公司':<18} {'分层':<3} {'分数':>4}  {'PIPL':<5} 来源")
    print("-" * 72)
    for l in leads_sorted:
        print(
            f"{l['id']:>3}  {str(l['company'])[:16]:<18} {str(l['tier']):<3} "
            f"{str(l['score']):>4}  {str(l['pilp_consent']):<5} {l['source']}"
        )
    print(f"共 {len(leads)} 条 SCORED")

    # ---------- 5. 触达（合规中间件强制拦截） ----------
    banner("5. 批量触达（SCORED → CONTACTED，逐条过合规）")
    code, body = call("post", "/outreach", params={"channel": "SMS"})
    sent, blocked, idem = 0, [], 0
    detail = body.get("detail", "")
    try:
        results = ast.literal_eval(detail) if detail.strip().startswith("[") else []
    except Exception:
        results = []
    for r in results:
        if r.get("blocked_by_compliance"):
            blocked.append(r.get("reason"))
        elif r.get("idempotent"):
            idem += 1
        elif r.get("ok"):
            sent += 1
    print(f"POST /outreach?channel=SMS -> {code}")
    print(f"  成功触达 {sent} 条 | 合规拦截 {len(blocked)} 条 | 幂等跳过 {idem} 条")
    for reason in blocked:
        print(f"    ✗ 拦截：{reason}")

    # ---------- 6. 待意向线索 ----------
    banner("6. 已触达线索（CONTACTED）")
    code, contacted = call("get", "/leads", params={"state": "CONTACTED"})
    for l in contacted:
        print(f"  #{l['id']:<3} {l['company']:<20} 分数={l['score']}")
    if not contacted:
        print("  （无可意向线索，后续签约演示跳过）")

    # ---------- 7. 标记意向 ----------
    lead = contacted[0] if contacted else None
    if lead:
        banner("7. 标记意向（CONTACTED → INTERESTED）")
        code, body = call("post", f"/leads/{lead['id']}/intent")
        print(f"POST /leads/{lead['id']}/intent -> {code}  {body.get('detail')}")

        # ---------- 8. 签约 ----------
        banner("8. 发起签约（INTERESTED → SIGNED，法大大通道/无凭据回退 mock）")
        code, body = call(
            "post", f"/leads/{lead['id']}/sign",
            json={"signer_name": "张经理", "signer_phone": lead["phone"] or "13900000000"},
        )
        print(f"POST /leads/{lead['id']}/sign -> {code}  {body.get('detail')}")

        # ---------- 9. 发货 ----------
        banner("9. 安排发货（SIGNED → SHIPPED，WMS + 快递鸟/mock）")
        code, body = call(
            "post", f"/leads/{lead['id']}/ship",
            json={
                "sku": "SUPPLY-BOX-01", "qty": 2,
                "receiver_name": "张经理", "receiver_phone": lead["phone"] or "13900000000",
                "receiver_address": "上海市浦东新区世纪大道 100 号",
            },
        )
        print(f"POST /leads/{lead['id']}/ship -> {code}  {body.get('detail')}")

        # ---------- 10. 物流轨迹 ----------
        banner("10. 查询物流轨迹")
        code, body = call("get", f"/leads/{lead['id']}/tracking")
        print(f"GET /leads/{lead['id']}/tracking -> {code}")
        print(jp(body))

    # ---------- 11. 合同 / 履约单 ----------
    banner("11. 合同与履约单总览")
    code, contracts = call("get", "/contracts")
    print(f"合同 {len(contracts)} 份：")
    for c in contracts:
        print(f"  #{c['id']} {c['contract_no']}  签约人={c['signer_name']}  状态={c['status']}  通道={c['provider']}")
    code, orders = call("get", "/orders")
    print(f"\n履约单 {len(orders)} 条：")
    for o in orders:
        print(f"  #{o['id']} SKU={o['sku']} x{o['qty']}  运单={o['tracking_no']}  物流={o['logistics_provider']}  状态={o['status']}")

    # ---------- 12. 审计日志 ----------
    banner("12. 审计日志（最近 10 条）")
    code, audits = call("get", "/audit")
    for a in audits[:10]:
        print(f"  [{a['event_type']:<20}] lead={a['lead_id']} agent={a['agent']:<18} {str(a['detail'])[:52]}")

    # ---------- 13. 系统设置：读写并验证生效 ----------
    banner("13. 系统设置：可视化配置读写（评分权重 + 合规频次上限）")
    code, settings = call("get", "/settings")
    print(f"GET /settings -> {code}")
    print(f"  评分权重（当前）：{jp(settings['scoring'])}")
    print(f"  合规频次上限（当前）：{settings['compliance']['frequency_cap']} 次 / "
          f"{settings['compliance']['frequency_window_days']} 天")

    code, updated = call(
        "put", "/settings",
        json={
            "scoring": {"credit_code_points": 50},
            "compliance": {"frequency_cap": 5},
        },
    )
    print(f"\nPUT /settings -> {code}")
    print(f"  评分 credit_code_points 改为：{updated['scoring']['credit_code_points']}")
    print(f"  合规 frequency_cap 改为：{updated['compliance']['frequency_cap']}")

    code, verify = call("get", "/settings")
    ok = (
        verify["scoring"]["credit_code_points"] == 50
        and verify["compliance"]["frequency_cap"] == 5
    )
    print(f"\n回读校验 -> {'✓ 配置已持久化并生效' if ok else '✗ 未生效'}")

    # ---------- 14. 状态漏斗 ----------
    banner("14. 线索状态漏斗")
    for st in ["NEW", "SCORED", "CONTACTED", "INTERESTED", "SIGNED", "SHIPPED"]:
        code, rows = call("get", "/leads", params={"state": st})
        print(f"  {st:<12} {'█' * len(rows)} {len(rows)}")

    print("\n演示完成 ✅\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
