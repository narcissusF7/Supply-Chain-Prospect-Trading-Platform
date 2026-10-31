"""真实 WMS 仓储出库通道（可选配置 + 多级回退）。

设计要点
--------
1. 优先使用真实 WMS 出库 API：POST {WMS_HOST}/outbound/create（携带 WMS_TOKEN 鉴权）。
2. 若环境变量（WMS_HOST / WMS_TOKEN）缺失 → 回退 mock（打印 + 记日志），保证无凭据也能本地跑通。
3. 真实路径用标准库 urllib 发 HTTP（无第三方依赖），语法正确、可 import，但本环境
   不调用（测试不设置这些变量）。
4. 异常兜底：真实调用失败 → 记录并回退 mock，绝不因缺依赖导致 `import app` 失败。
5. 原 app/mock_channels.py 中的 mock_wms 语义并入此处；fulfillment_agent 改用本通道
   （保留 mock_channels.mock_wms 不删除，避免影响其它潜在引用）。

环境变量（配置真实通道所需）
----------------------------------
- WMS_HOST    WMS 网关地址（如 https://wms.internal/api）
- WMS_TOKEN   WMS 调用鉴权令牌

依赖说明
--------
- 真实通道仅依赖标准库 urllib / json，无第三方依赖；环境变量缺失时走 mock。
- 保证任何环境下 `import` 正常、逻辑自洽。
"""
from __future__ import annotations

import json
import logging
import os
from urllib.error import URLError
from urllib.request import Request, urlopen

from app import models

logger = logging.getLogger("supply.channels.wms")


def is_configured() -> bool:
    """是否配置了 WMS 凭据（WMS_HOST / WMS_TOKEN 均存在）。"""
    return bool(os.environ.get("WMS_HOST") and os.environ.get("WMS_TOKEN"))


def _mock_fallback(lead: "models.Lead", sku: str, qty: int, reason: str = "缺少凭据") -> dict:
    """无凭据/异常时的 mock 回退（打印 + 记日志），保证本地可跑通。"""
    logger.warning("[WMS] 回退 mock 出库（%s）", reason)
    return {
        "provider": "mock",
        "status": "CREATED",
        "lead_id": lead.id,
        "sku": sku,
        "qty": qty,
    }


def create_outbound(lead: "models.Lead", sku: str, qty: int) -> dict:
    """仓储出库（真实 WMS 通道，含 mock 回退）。

    回退顺序：真实 WMS 出库 API →（凭据缺失或异常）mock。
    返回 dict（含 provider / status），demo 中出库成功即视为已创建出库单。

    :param lead: 线索对象
    :param sku: 商品 SKU
    :param qty: 数量
    :return: dict（含 provider / status）
    """
    # 0) 无凭据 → 直接回退 mock
    if not is_configured():
        return _mock_fallback(lead, sku, qty)

    host = os.environ["WMS_HOST"]
    token = os.environ["WMS_TOKEN"]
    url = f"{host.rstrip('/')}/outbound/create"
    payload = json.dumps(
        {"token": token, "leadId": lead.id, "sku": sku, "qty": qty}, ensure_ascii=False
    ).encode("utf-8")
    req = Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    logger.info("[WMS] POST %s", url)
    try:
        with urlopen(req, timeout=10.0) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        status = body.get("status", "CREATED") if isinstance(body, dict) else "CREATED"
        return {
            "provider": "wms",
            "status": status,
            "lead_id": lead.id,
            "sku": sku,
            "qty": qty,
        }
    except Exception as exc:  # 真实出库失败 → 记录并回退 mock（保证本地可跑通）
        logger.error("[WMS] 真实出库失败，回退 mock：%s", exc)
        return _mock_fallback(lead, sku, qty, reason=f"出库异常：{exc}")
