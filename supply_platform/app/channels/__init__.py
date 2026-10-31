"""外部通道包。

目前包含真实短信通道 app.channels.aliyun_sms（阿里云短信，含多级回退）。
所有通道统一约定：发送前必过合规中间件，合规不通过绝不调用外部接口。
"""
from __future__ import annotations
