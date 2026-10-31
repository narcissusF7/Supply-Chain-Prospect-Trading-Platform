"""合规守护中间件（横切关注点）。

在任意触达动作之前，强制走 ComplianceGuard.check(lead)，任一不通过即阻断。
校验项（任一命中即拦截，按优先级短路）：
1. PILP 同意标志 必须为 True
2. 退订名单 (OPT_OUT)
3. 谢绝来电登记 (DO_NOT_CALL)
4. 呼叫时段 09:00–21:00（外呼强约束；短信放宽到允许但记录）
5. 频次上限：7 日内同一线索触达 ≤ 3 次

设计意图：合规模块为横切关注点，独立于各 agent，触达前必过。
返回 (allow, reason) 而非抛异常，便于调用方记录审计后阻断。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.config_store import get_compliance_config
from app.db import SessionLocal  # 默认独立会话，体现横切隔离

# 以下常量保留为「出厂默认」说明，实际值由合规配置（config_store）提供，
# 使「系统设置 → 合规配置」可视化编辑真正生效。
FREQUENCY_WINDOW_DAYS = 7
FREQUENCY_CAP = 3
CALL_START_HOUR = 9
CALL_END_HOUR = 21


class ComplianceGuard:
    """合规守护：纯函数式 check，返回 (allow, reason)。"""

    @staticmethod
    def _now() -> datetime:
        # 预留：未来接真实时钟/时区服务
        return datetime.now()

    @staticmethod
    def check(
        lead: "models.Lead",
        channel: str = "SMS",
        session: Session | None = None,
    ) -> tuple[bool, str]:
        """对单条线索做合规校验。

        :param lead: 线索对象
        :param channel: 触达渠道 SMS / OUTBOUND
        :param session: 可选外部会话；不传则内部新建（隔离）
        :return: (allow, reason)
        """
        own_session = False
        if session is None:
            session = SessionLocal()
            own_session = True
        try:
            now = ComplianceGuard._now()
            cfg = get_compliance_config(session)

            # 1) PILP 同意（可配置开关）
            if cfg.get("require_pilp_consent", True) and not lead.pilp_consent:
                return False, "未获得 PIPL 同意（pilp_consent=False），阻断触达"

            # 2) 退订名单
            opt_out = session.execute(
                select(models.ComplianceList).where(
                    models.ComplianceList.type == "OPT_OUT",
                    models.ComplianceList.key.in_([lead.phone, lead.credit_code]),
                )
            ).scalars().first()
            if opt_out is not None:
                return False, f"命中退订名单（key={opt_out.key}），阻断触达"

            # 3) 谢绝来电
            dnc = session.execute(
                select(models.ComplianceList).where(
                    models.ComplianceList.type == "DO_NOT_CALL",
                    models.ComplianceList.key.in_([lead.phone, lead.credit_code]),
                )
            ).scalars().first()
            if dnc is not None:
                return False, f"命中谢绝来电登记（key={dnc.key}），阻断触达"

            # 4) 呼叫时段（OUTBOUND 强约束；SMS 放宽；可配置开关与时段）
            if channel == "OUTBOUND" and cfg.get("enforce_call_window", True):
                hour = now.hour
                start = int(cfg.get("call_start_hour", CALL_START_HOUR))
                end = int(cfg.get("call_end_hour", CALL_END_HOUR))
                if not (start <= hour < end):
                    return False, (
                        f"非允许呼叫时段（{hour}:00，需在 {start}:00–{end}:00）"
                    )

            # 5) 频次上限（仅统计成功触达；窗口与上限可配置）
            window_days = int(cfg.get("frequency_window_days", FREQUENCY_WINDOW_DAYS))
            cap = int(cfg.get("frequency_cap", FREQUENCY_CAP))
            window_start = now - timedelta(days=window_days)
            count = session.execute(
                select(func.count(models.ContactTask.id)).where(
                    models.ContactTask.lead_id == lead.id,
                    models.ContactTask.created_at >= window_start,
                )
            ).scalar_one()
            if count >= cap:
                return False, f"{window_days} 日内触达 {count} 次，已达上限 {cap} 次"

            return True, "合规校验通过"
        finally:
            if own_session:
                session.close()
