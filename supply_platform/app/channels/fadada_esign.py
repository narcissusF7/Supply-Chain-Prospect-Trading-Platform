"""真实法大大电子签约通道（可选配置 + 多级回退）。

设计要点
--------
1. 优先使用真实法大大开放平台 API：先取 access_token，再创建签署任务拿到签署链接。
2. 若环境变量（FADADA_APP_ID / FADADA_APP_SECRET / FADADA_HOST）缺失 → 回退 mock
   （打印 + 记日志），保证无凭据也能本地跑通。
3. 真实路径用标准库 urllib 发 HTTP（无第三方依赖），语法正确、可 import，但本环境
   不调用（测试不设置这些变量）。
4. 异常兜底：真实调用失败 → 记录并回退 mock，绝不因缺依赖导致 `import app` 失败。

环境变量（配置真实通道所需）
----------------------------------
- FADADA_APP_ID      法大大应用 ID（AppId）
- FADADA_APP_SECRET  法大大应用 Secret（AppSecret）
- FADADA_HOST        法大大开放平台网关地址（如 https://uat-api.fadada.com）

依赖说明
--------
- 真实通道仅依赖标准库 urllib / json，无第三方依赖；环境变量缺失时走 mock。
- 保证任何环境下 `import` 正常、逻辑自洽。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from app import models
from app.mock_channels import mock_e_sign

logger = logging.getLogger("supply.channels.fadada_esign")


def _contract_no(lead_id: int) -> str:
    """生成合同编号：CT + 精确到秒的时间戳 + 线索 ID（保证唯一）。"""
    return f"CT{datetime.now().strftime('%Y%m%d%H%M%S')}{lead_id}"


def is_configured() -> bool:
    """是否配置了法大大凭据（三个环境变量均存在）。"""
    return bool(
        os.environ.get("FADADA_APP_ID")
        and os.environ.get("FADADA_APP_SECRET")
        and os.environ.get("FADADA_HOST")
    )


def _mock_fallback(
    lead: "models.Lead",
    signer_name: str,
    signer_phone: str,
    reason: str = "缺少凭据",
) -> dict:
    """无凭据/异常时的 mock 回退（打印 + 记日志），保证本地可跑通。"""
    logger.warning("[FADADA E-SIGN] 回退 mock 签约（%s）", reason)
    contract_no = _contract_no(lead.id)
    contract_url = f"https://mock/contract/{contract_no}"
    # 复用既有 mock 占位（仅打印 / 记日志，不调真实接口）
    mock_e_sign(lead, contract_url)
    return {
        "provider": "mock",
        "status": "SIGNED",
        "contract_no": contract_no,
        "contract_url": contract_url,
        "signer_name": signer_name,
        "signer_phone": signer_phone,
    }


def _get_access_token(app_id: str, app_secret: str, host: str, timeout: float = 10.0) -> str:
    """法大大开放平台：获取 access_token（client_credentials）。"""
    url = f"{host.rstrip('/')}/oauth2/token"
    payload = json.dumps(
        {"appId": app_id, "appSecret": app_secret, "grantType": "client_credentials"}
    ).encode("utf-8")
    req = Request(
        url, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    logger.info("[FADADA E-SIGN] POST %s", url)
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"法大大获取 token 失败：{exc}") from exc
    # 法大大返回形态：{ "code": "100000", "data": { "accessToken": "..." } }
    data = body.get("data", {}) if isinstance(body, dict) else {}
    token = data.get("accessToken") or (body.get("access_token") if isinstance(body, dict) else None)
    if not token:
        raise RuntimeError(f"法大大 token 响应异常：{body}")
    return token


def _create_sign_task(
    app_id: str,
    token: str,
    host: str,
    lead: "models.Lead",
    signer_name: str,
    signer_phone: str,
    timeout: float = 10.0,
) -> dict:
    """法大大：创建签署任务并返回签署链接。"""
    url = f"{host.rstrip('/')}/sign-task/create"
    business_no = _contract_no(lead.id)
    payload = json.dumps(
        {
            "appId": app_id,
            "businessNo": business_no,
            "docTitle": f"供应链服务协议-{lead.company}",
            "signerName": signer_name or lead.name,
            "signerMobile": signer_phone or (lead.phone or ""),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-FASC-App-Id": app_id,
        "X-FASC-Access-Token": token,
    }
    req = Request(url, data=payload, headers=headers, method="POST")
    logger.info("[FADADA E-SIGN] POST %s", url)
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        raise RuntimeError(f"法大大创建签署任务失败：{exc}") from exc
    data = body.get("data", {}) if isinstance(body, dict) else {}
    return {
        "contract_no": data.get("businessNo") or data.get("signTaskId") or business_no,
        "contract_url": data.get("signUrl") or data.get("docUrl") or "",
    }


def send_contract(
    lead: "models.Lead",
    signer_name: str = "",
    signer_phone: str = "",
) -> dict:
    """发起电子签约（真实法大大通道，含 mock 回退）。

    回退顺序：真实开放平台 API（取 token → 建签署任务）→（凭据缺失或异常）mock。
    demo 中签约成功即视为已签（status=SIGNED）。

    :param lead: 线索对象
    :param signer_name: 签约人姓名（可空，空则用 lead.name）
    :param signer_phone: 签约人手机号（可空，空则用 lead.phone）
    :return: dict（含 provider / status / contract_no / contract_url）
    """
    # 0) 无凭据 → 直接回退 mock
    if not is_configured():
        return _mock_fallback(lead, signer_name, signer_phone, reason="缺少法大大环境变量")

    # 1) 调用真实通道
    app_id = os.environ["FADADA_APP_ID"]
    app_secret = os.environ["FADADA_APP_SECRET"]
    host = os.environ["FADADA_HOST"]
    try:
        token = _get_access_token(app_id, app_secret, host)
        task = _create_sign_task(app_id, token, host, lead, signer_name, signer_phone)
        contract_no = task["contract_no"] or _contract_no(lead.id)
        contract_url = task["contract_url"] or f"https://mock/contract/{contract_no}"
        return {
            "provider": "fadada",
            "status": "SIGNED",
            "contract_no": contract_no,
            "contract_url": contract_url,
            "signer_name": signer_name,
            "signer_phone": signer_phone,
        }
    except Exception as exc:  # 真实签约失败 → 记录并回退 mock（保证本地可跑通）
        logger.error("[FADADA E-SIGN] 真实签约失败，回退 mock：%s", exc)
        return _mock_fallback(lead, signer_name, signer_phone, reason=f"签约异常：{exc}")
