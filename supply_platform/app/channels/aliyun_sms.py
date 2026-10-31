"""真实阿里云短信通道（可选依赖 + 多级回退）。

设计要点
--------
1. 优先使用官方 SDK `alibabacloud_dysmsapi20170525`（需 `pip install`）。
2. 若官方 SDK 不可用，自动回退到「RPC 签名 V1 原始 HTTP」实现
   （HMAC-SHA1 签名，Action=SendSms，Version=2017-05-25，RegionId=cn-hangzhou，
   参数 SignName / TemplateCode / PhoneNumbers / TemplateParam），严格按阿里云 RPC 签名规范拼接。
3. 若环境变量（ALIYUN_SMS_ACCESS_KEY_ID 等）缺失 → 回退 mock（打印 + 记日志），
   保证无凭据也能本地跑通（见文件顶部注释：回退策略）。
4. 发送前强制过合规中间件 ComplianceGuard.check（退订 / 谢绝来电 / 时段 / 频次 / PIPL），
   合规不通过绝不调用短信接口。

环境变量（配置真实通道所需）
----------------------------------
- ALIYUN_SMS_ACCESS_KEY_ID
- ALIYUN_SMS_ACCESS_KEY_SECRET
- ALIYUN_SMS_SIGN_NAME
- ALIYUN_SMS_TEMPLATE_CODE

依赖说明
--------
- 官方 SDK 与第三方 HTTP 库均为可选（import 容错）：官方 SDK 缺失时走 RPC（用标准库 urllib，
  无第三方依赖）；环境变量缺失时走 mock。保证任何环境下 `import` 正常、逻辑自洽。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import urlopen

from app import models
from app.compliance import ComplianceGuard
from app.mock_channels import mock_sms_send

logger = logging.getLogger("supply.channels.aliyun_sms")

# 阿里云短信网关
_ALIYUN_SMS_ENDPOINT = "https://dysmsapi.aliyuncs.com/"
_ALIYUN_SMS_VERSION = "2017-05-25"
_ALIYUN_SMS_REGION_ID = "cn-hangzhou"

# 官方 SDK 是否可用（import 容错）
try:  # pragma: no cover - 取决于运行环境是否安装 SDK
    from alibabacloud_dysmsapi20170525.client import Client as _DysmsClient  # type: ignore
    from alibabacloud_dysmsapi20170525 import models as _dysms_models  # type: ignore
    from alibabacloud_tea_openapi import models as _open_api_models  # type: ignore
    from alibabacloud_tea_util import models as _tea_util_models  # type: ignore
    _ALIYUN_SDK_AVAILABLE = True
except Exception as exc:  # pragma: no cover
    logger.warning("阿里云短信官方 SDK 未安装，回退 RPC 签名实现：%s", exc)
    _ALIYUN_SDK_AVAILABLE = False


def is_configured() -> bool:
    """是否配置了阿里云短信凭据（四个环境变量均存在）。"""
    return bool(
        os.environ.get("ALIYUN_SMS_ACCESS_KEY_ID")
        and os.environ.get("ALIYUN_SMS_ACCESS_KEY_SECRET")
        and os.environ.get("ALIYUN_SMS_SIGN_NAME")
        and os.environ.get("ALIYUN_SMS_TEMPLATE_CODE")
    )


def _utc_iso8601() -> str:
    """阿里云要求的 ISO8601 UTC 时间戳：YYYY-MM-DDTHH:mm:ssZ。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _percent_encode(text: str) -> str:
    """阿里云 RPC 签名百分号编码：A-Za-z0-9-_.~ 不编码，其余按 %XY（大写十六进制）。"""
    result: list[str] = []
    for byte in text.encode("utf-8"):
        if (
            48 <= byte <= 57  # 0-9
            or 65 <= byte <= 90  # A-Z
            or 97 <= byte <= 122  # a-z
            or byte in (45, 46, 95, 126)  # - . _ ~
        ):
            result.append(chr(byte))
        else:
            result.append("%%%02X" % byte)
    return "".join(result)


def _compose_signature(params: dict, access_key_secret: str) -> str:
    """按阿里云 RPC 签名 V1 规范生成 Signature（HMAC-SHA1 + Base64）。"""
    # 1) 参数按 key 字典序排序，拼接规范查询串
    canonical = "&".join(
        f"{_percent_encode(str(k))}={_percent_encode(str(v))}"
        for k, v in sorted(params.items())
    )
    # 2) 构造待签字符串：GET&%2F&<编码后的规范串>
    string_to_sign = "GET&%2F&" + _percent_encode(canonical)
    # 3) HMAC-SHA1，密钥为 AccessKeySecret 末尾追加 '&'
    key = (access_key_secret + "&").encode("utf-8")
    digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def _build_template_param(lead: "models.Lead", content: str) -> str:
    """构造 TemplateParam（JSON 字符串）。默认使用 `content` 变量；
    真实模板需包含同名变量，或按需调整本函数映射业务字段。"""
    return json.dumps({"content": content}, ensure_ascii=False)


def _rpc_send_sms(
    access_key_id: str,
    access_key_secret: str,
    sign_name: str,
    template_code: str,
    phone: str,
    template_param: str,
    timeout: float = 10.0,
) -> dict:
    """RPC 签名 V1 原始 HTTP 发送（标准库 urllib，无第三方依赖）。"""
    params: dict = {
        "AccessKeyId": access_key_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": _ALIYUN_SMS_REGION_ID,
        "SignName": sign_name,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": str(uuid.uuid4()),
        "SignatureVersion": "1.0",
        "TemplateCode": template_code,
        "TemplateParam": template_param,
        "Timestamp": _utc_iso8601(),
        "Version": _ALIYUN_SMS_VERSION,
    }
    params["Signature"] = _compose_signature(params, access_key_secret)
    query = "&".join(
        f"{_percent_encode(str(k))}={_percent_encode(str(v))}"
        for k, v in sorted(params.items())
    )
    url = _ALIYUN_SMS_ENDPOINT + "?" + query
    logger.info("[ALIYUN SMS][RPC] GET %s", _ALIYUN_SMS_ENDPOINT)
    try:
        with urlopen(url, timeout=timeout) as resp:  # noqa: S310 - 固定官方域名
            body = resp.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"阿里云短信 RPC 调用失败：{exc}") from exc
    return json.loads(body)


def _sdk_send_sms(
    access_key_id: str,
    access_key_secret: str,
    sign_name: str,
    template_code: str,
    phone: str,
    template_param: str,
) -> dict:
    """使用官方 SDK 发送（需 alibabacloud_dysmsapi20170525）。"""
    config = _open_api_models.Config(
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )
    config.endpoint = "dysmsapi.aliyuncs.com"
    client = _DysmsClient(config)
    request = _dysms_models.SendSmsRequest(
        phone_numbers=phone,
        sign_name=sign_name,
        template_code=template_code,
        template_param=template_param,
    )
    runtime = _tea_util_models.RuntimeOptions()
    resp = client.send_sms_with_options(request, runtime)
    # Tea 模型转 dict 便于统一处理
    return resp.body.to_map() if hasattr(resp, "body") and hasattr(resp.body, "to_map") else {}


def _mock_fallback(lead: "models.Lead", content: str, reason: str = "缺少凭据") -> dict:
    """无凭据/异常时的 mock 回退（打印 + 记日志），保证本地可跑通。"""
    logger.warning("[ALIYUN SMS] 回退 mock 发送（%s）", reason)
    return mock_sms_send(lead, content)


def send_sms(lead: "models.Lead", content: str, session: "object | None" = None) -> dict:
    """发送短信（真实阿里云通道，含多级回退）。

    回退顺序：官方 SDK → RPC 签名 V1 原始 HTTP →（凭据缺失或异常）mock。
    发送前必过合规校验，合规不通过绝不调用短信接口。

    :param lead: 线索对象
    :param content: 短信正文（作为 TemplateParam 的 content 变量）
    :param session: 可选外部会话；用于合规预校验（只读，不写审计）
    :return: 发送回执 dict（含 channel / lead_id / phone / status / provider 等）
    """
    # 0) 无凭据 → 直接回退 mock
    if not is_configured():
        return _mock_fallback(lead, content, reason="缺少阿里云短信环境变量")

    # 1) 合规前置校验（防御性；marketing_agent.outreach 已校验，此处不写审计）
    own_session = False
    if session is None:
        from app.db import SessionLocal
        session = SessionLocal()
        own_session = True
    try:
        allow, reason = ComplianceGuard.check(lead, channel="SMS", session=session)
    finally:
        if own_session:
            session.close()
    if not allow:
        logger.warning("[ALIYUN SMS] 合规拦截，未发送：%s", reason)
        return {
            "channel": "SMS",
            "lead_id": lead.id,
            "phone": lead.phone,
            "status": "COMPLIANCE_BLOCKED",
            "provider": "none",
            "reason": reason,
        }

    # 2) 调用真实通道
    access_key_id = os.environ["ALIYUN_SMS_ACCESS_KEY_ID"]
    access_key_secret = os.environ["ALIYUN_SMS_ACCESS_KEY_SECRET"]
    sign_name = os.environ["ALIYUN_SMS_SIGN_NAME"]
    template_code = os.environ["ALIYUN_SMS_TEMPLATE_CODE"]
    template_param = _build_template_param(lead, content)

    try:
        if _ALIYUN_SDK_AVAILABLE:
            receipt = _sdk_send_sms(
                access_key_id, access_key_secret, sign_name, template_code,
                str(lead.phone), template_param,
            )
        else:
            receipt = _rpc_send_sms(
                access_key_id, access_key_secret, sign_name, template_code,
                str(lead.phone), template_param,
            )
        return {
            "channel": "SMS",
            "lead_id": lead.id,
            "phone": lead.phone,
            "status": "SENT",
            "provider": "aliyun",
            "sdk": "official" if _ALIYUN_SDK_AVAILABLE else "rpc_v1",
            "receipt": receipt,
        }
    except Exception as exc:  # 真实发送失败 → 记录并回退 mock（保证本地可跑通）
        logger.error("[ALIYUN SMS] 真实发送失败，回退 mock：%s", exc)
        return _mock_fallback(lead, content, reason=f"发送异常：{exc}")
