"""真实快递鸟物流通道（可选配置 + 多级回退）。

设计要点
--------
1. 优先使用真实快递鸟开放平台 API：电子面单/即时下单（RequestType=1001）拿到物流单号，
   即时查询（RequestType=1002）查询物流轨迹。
2. 若环境变量（KDNIAO_APP_KEY / KDNIAO_APP_SECRET / KDNIAO_EBUSINESS_ID / KDNIAO_HOST）
   缺失 → 回退 mock（打印 + 记日志），保证无凭据也能本地跑通。
3. 真实路径用标准库 urllib 发 HTTP，按快递鸟规范做 MD5 签名（DataSign = Base64(MD5(Json+AppKey))），
   无第三方依赖；语法正确、可 import，但本环境不调用（测试不设置这些变量）。
4. 异常兜底：真实调用失败 → 记录并回退 mock，绝不因缺依赖导致 `import app` 失败。

环境变量（配置真实通道所需）
----------------------------------
- KDNIAO_APP_KEY        快递鸟用户 AppKey（业务标识）
- KDNIAO_APP_SECRET     快递鸟 AppSecret（用于 DataSign 签名）
- KDNIAO_EBUSINESS_ID   快递鸟商户 ID（EBusinessID）
- KDNIAO_HOST           快递鸟网关地址（如 https://api.kdniao.com）

依赖说明
--------
- 真实通道仅依赖标准库 urllib / json / hashlib / base64，无第三方依赖；环境变量缺失时走 mock。
- 保证任何环境下 `import` 正常、逻辑自洽。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import urllib.parse
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from app import models

logger = logging.getLogger("supply.channels.kdniao_logistics")

# 快递鸟业务类型编码
_KDNIAO_ORDER_REQUEST_TYPE = "1001"  # 即时下单（或 8001 电子面单）
_KDNIAO_TRACK_REQUEST_TYPE = "1002"  # 即时查询物流轨迹
_DATA_TYPE = "2"  # JSON
_DEFAULT_SHIPPER = "YTO"  # 示例快递公司编码（圆通）


def is_configured() -> bool:
    """是否配置了快递鸟凭据（四个环境变量均存在）。"""
    return bool(
        os.environ.get("KDNIAO_APP_KEY")
        and os.environ.get("KDNIAO_APP_SECRET")
        and os.environ.get("KDNIAO_EBUSINESS_ID")
        and os.environ.get("KDNIAO_HOST")
    )


def _md5_sign(data_json: str, app_secret: str) -> str:
    """快递鸟 DataSign：MD5(明文 JSON + AppSecret) 取小写 32 位十六进制，再 Base64。"""
    raw = (data_json + app_secret).encode("utf-8")
    md5_hex = hashlib.md5(raw).hexdigest()
    return base64.b64encode(md5_hex.encode("utf-8")).decode("ascii")


def _post(req_type: str, data_json: str, app_secret: str, e_business_id: str, host: str, timeout: float = 10.0) -> dict:
    """快递鸟统一请求：构造带签名的表单请求并 POST 网关。"""
    params = {
        "RequestData": data_json,
        "EBusinessID": e_business_id,
        "RequestType": req_type,
        "DataSign": _md5_sign(data_json, app_secret),
        "DataType": _DATA_TYPE,
    }
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = Request(
        host, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST",
    )
    logger.info("[KDNIAO] POST %s RequestType=%s", host, req_type)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"快递鸟接口调用失败：{exc}") from exc


def _mock_order(
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
    sku: str,
    qty: int,
    lead: "models.Lead",
    reason: str = "缺少凭据",
) -> dict:
    """无凭据/异常时的 mock 回退（打印 + 记日志），保证本地可跑通。"""
    logger.warning("[KDNIAO] 回退 mock 下单（%s）", reason)
    tracking_no = f"KDMOCK{lead.id}{qty}{int(datetime.now().timestamp())}"
    return {
        "provider": "mock",
        "tracking_no": tracking_no,
        "status": "SHIPPED",
        "receiver_name": receiver_name,
        "receiver_phone": receiver_phone,
        "receiver_address": receiver_address,
    }


def create_order(
    receiver_name: str,
    receiver_phone: str,
    receiver_address: str,
    sku: str,
    qty: int,
    lead: "models.Lead",
) -> dict:
    """创建物流订单（真实快递鸟通道，含 mock 回退）。

    回退顺序：真实电子面单/下单 API →（凭据缺失或异常）mock。
    返回 dict（含 provider / tracking_no / status），demo 中下单成功即视为已发货。

    :param receiver_name: 收件人姓名（可空）
    :param receiver_phone: 收件人手机号（可空）
    :param receiver_address: 收件地址（可空）
    :param sku: 商品 SKU
    :param qty: 数量
    :param lead: 线索对象（用于生成订单号与默认收件信息）
    :return: dict（含 provider / tracking_no / status）
    """
    # 0) 无凭据 → 直接回退 mock
    if not is_configured():
        return _mock_order(receiver_name, receiver_phone, receiver_address, sku, qty, lead)

    app_key = os.environ["KDNIAO_APP_KEY"]
    app_secret = os.environ["KDNIAO_APP_SECRET"]
    e_business_id = os.environ["KDNIAO_EBUSINESS_ID"]
    host = os.environ["KDNIAO_HOST"]

    data = {
        "OrderCode": f"ORDER{lead.id}{qty}{int(datetime.now().timestamp())}",
        "ShipperCode": _DEFAULT_SHIPPER,
        "PayType": 1,
        "ExpType": 1,
        "Receiver": {
            "Name": receiver_name or lead.name,
            "Mobile": receiver_phone or (lead.phone or ""),
            "Address": receiver_address or lead.company,
        },
        "Commodity": [{"GoodsName": sku, "GoodsQuantity": qty}],
    }
    data_json = json.dumps(data, ensure_ascii=False)
    try:
        resp = _post(_KDNIAO_ORDER_REQUEST_TYPE, data_json, app_secret, e_business_id, host)
        tracking_no = resp.get("LogisticCode") or resp.get("tracking_no")
        if not tracking_no:
            raise RuntimeError(f"快递鸟下单响应缺少物流单号：{resp}")
        return {
            "provider": "kdniao",
            "tracking_no": tracking_no,
            "status": "SHIPPED",
            "receiver_name": receiver_name,
            "receiver_phone": receiver_phone,
            "receiver_address": receiver_address,
        }
    except Exception as exc:  # 真实下单失败 → 记录并回退 mock（保证本地可跑通）
        logger.error("[KDNIAO] 真实下单失败，回退 mock：%s", exc)
        return _mock_order(
            receiver_name, receiver_phone, receiver_address, sku, qty, lead,
            reason=f"下单异常：{exc}",
        )


def _mock_tracking(tracking_no: str, reason: str = "缺少凭据") -> dict:
    """无凭据/异常时的 mock 轨迹回退（打印 + 记日志），保证本地可跑通。"""
    logger.warning("[KDNIAO] 回退 mock 轨迹查询（%s）", reason)
    return {
        "provider": "mock",
        "status": "SHIPPED",
        "tracking_no": tracking_no,
        "traces": [
            {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "desc": "【mock】已揽收"},
            {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "desc": "【mock】运输中"},
        ],
    }


def query_tracking(tracking_no: str) -> dict:
    """查询物流轨迹（真实快递鸟通道，含 mock 回退）。

    返回 dict（含 provider / status / traces 列表），traces 为
    [{time, desc}, ...] 形态，便于前端直接渲染。

    :param tracking_no: 物流单号
    :return: dict（含 provider / status / traces）
    """
    # 0) 无凭据或单号为空 → 直接回退 mock
    if not is_configured() or not tracking_no:
        return _mock_tracking(tracking_no)

    app_secret = os.environ["KDNIAO_APP_SECRET"]
    e_business_id = os.environ["KDNIAO_EBUSINESS_ID"]
    host = os.environ["KDNIAO_HOST"]

    data = {"LogisticCode": tracking_no, "ShipperCode": _DEFAULT_SHIPPER}
    data_json = json.dumps(data, ensure_ascii=False)
    try:
        resp = _post(_KDNIAO_TRACK_REQUEST_TYPE, data_json, app_secret, e_business_id, host)
        traces: list[dict] = []
        for t in resp.get("Traces", []) if isinstance(resp, dict) else []:
            traces.append(
                {"time": t.get("AcceptTime", ""), "desc": t.get("AcceptStation", "")}
            )
        # 快递鸟 State：1 在途 / 2 揽收 / 3 疑难 / 4 到达 / 5 派件 / 6 已签收
        raw_state = str(resp.get("State", "SHIPPED")) if isinstance(resp, dict) else "SHIPPED"
        status = "SHIPPED" if raw_state in ("1", "2", "4", "5") else raw_state
        return {
            "provider": "kdniao",
            "status": status,
            "tracking_no": tracking_no,
            "traces": traces,
        }
    except Exception as exc:  # 真实查询失败 → 记录并回退 mock（保证本地可跑通）
        logger.error("[KDNIAO] 真实轨迹查询失败，回退 mock：%s", exc)
        return _mock_tracking(tracking_no, reason=f"查询异常：{exc}")
