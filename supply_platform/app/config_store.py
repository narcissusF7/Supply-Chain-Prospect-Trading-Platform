"""系统配置存储：采集 / 评分 / 合规 的可视化配置单一事实源。

设计要点
--------
- 配置以「段（section）」为单位存储于 system_configs 表，每段是一份完整 JSON。
- 未写入任何段时，返回 DEFAULT_CONFIG 中对应段的默认值；写入后以库内值为准。
- 更新采用「提供值覆盖默认值」的合并策略：前端只需传要改的字段，其余保留默认。
- 业务逻辑（data_agent.score / ComplianceGuard.check / collect）从此处读取，
  使「系统设置」页面的可视化配置真正生效，而非仅展示。

配置段与字段（默认值见 DEFAULT_CONFIG）
----------------------------------------
collection（采集）:
  source          数据源标识（默认 "api_mock"；未来接第三方 API 名）
  min_employees   员工规模过滤下限，低于此值的商户不采集（默认 0 = 不过滤）
  allowed_regions 允许采集的区域列表（默认 [] = 全部区域）
  batch_size      单次采集最大条数（默认 100，演示性阈值）

scoring（评分）:
  credit_code_points   有统一社会信用代码加分（默认 30）
  emp_threshold_high   员工规模「高」阈值（>= 取 emp_high_points，默认 100）
  emp_high_points      高规模加分（默认 30）
  emp_threshold_mid    员工规模「中」阈值（>= 取 emp_mid_points，默认 20）
  emp_mid_points       中规模加分（默认 20）
  emp_low_points       小规模加分（默认 10）
  region_tier1_points  一线区域加分（默认 20）
  region_other_points  其他区域加分（默认 10）
  tier1_regions        一线区域列表（默认 5 个一线城市）
  pilp_points          已获 PIPL 同意加分（默认 20）
  tier_a_min / tier_b_min  分层阈值（A>=80, B>=50, 否则 C）

compliance（合规）:
  require_pilp_consent 是否强制 PIPL 同意（默认 True）
  enforce_call_window  是否对 OUTBOUND 强制呼叫时段（默认 True）
  call_start_hour      允许呼叫起始小时（默认 9）
  call_end_hour        允许呼叫结束小时（默认 21）
  frequency_window_days 频次统计窗口天数（默认 7）
  frequency_cap        窗口内最大触达次数（默认 3）
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

# 三段默认值（即「系统设置」未改时的出厂配置）
DEFAULT_CONFIG: dict[str, dict[str, Any]] = {
    "collection": {
        "source": "api_mock",
        "min_employees": 0,
        "allowed_regions": [],
        "batch_size": 100,
    },
    "scoring": {
        "credit_code_points": 30,
        "emp_threshold_high": 100,
        "emp_high_points": 30,
        "emp_threshold_mid": 20,
        "emp_mid_points": 20,
        "emp_low_points": 10,
        "region_tier1_points": 20,
        "region_other_points": 10,
        "tier1_regions": ["beijing", "shanghai", "shenzhen", "guangzhou", "hangzhou"],
        "pilp_points": 20,
        "tier_a_min": 80,
        "tier_b_min": 50,
    },
    "compliance": {
        "require_pilp_consent": True,
        "enforce_call_window": True,
        "call_start_hour": 9,
        "call_end_hour": 21,
        "frequency_window_days": 7,
        "frequency_cap": 3,
    },
}

SECTION_KEYS = tuple(DEFAULT_CONFIG.keys())
SECTION_DESCRIPTIONS = {
    "collection": "采集配置",
    "scoring": "评分配置",
    "compliance": "合规配置",
}


def _merge(section: str, override: dict[str, Any]) -> dict[str, Any]:
    """将 override 覆盖到该段默认值上，返回合并后的完整段（浅合并，仅一层）。"""
    base = dict(DEFAULT_CONFIG[section])
    for k, v in (override or {}).items():
        # 仅接受已知键，忽略未知字段，避免脏数据写入
        if k in base:
            base[k] = v
    return base


def get_section(session: Session, section: str) -> dict[str, Any]:
    """读取某段配置：库内有则解析 JSON，否则回退默认值。"""
    if section not in DEFAULT_CONFIG:
        raise KeyError(f"未知配置段：{section}")
    row = session.get(models.SystemConfig, section)
    if row is None:
        return dict(DEFAULT_CONFIG[section])
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return dict(DEFAULT_CONFIG[section])


def get_all(session: Session) -> dict[str, dict[str, Any]]:
    """读取全部三段配置（合并默认值）。"""
    return {section: get_section(session, section) for section in DEFAULT_CONFIG}


def get_scoring_config(session: Session) -> dict[str, Any]:
    """读取评分配置段。"""
    return get_section(session, "scoring")


def get_compliance_config(session: Session) -> dict[str, Any]:
    """读取合规配置段。"""
    return get_section(session, "compliance")


def set_section(session: Session, section: str, override: dict[str, Any]) -> dict[str, Any]:
    """合并并持久化某段配置，返回写入后的完整段。"""
    if section not in DEFAULT_CONFIG:
        raise KeyError(f"未知配置段：{section}")
    merged = _merge(section, override)
    raw = json.dumps(merged, ensure_ascii=False)
    row = session.get(models.SystemConfig, section)
    if row is None:
        row = models.SystemConfig(
            key=section, value=raw,
            description=SECTION_DESCRIPTIONS.get(section),
        )
        session.add(row)
    else:
        row.value = raw
        row.description = SECTION_DESCRIPTIONS.get(section)
        row.updated_at = datetime.now()
    session.flush()
    return merged


def set_all(session: Session, payload: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """批量更新若干段（仅处理已知段）。返回更新后的全量配置。"""
    for section, override in (payload or {}).items():
        if section in DEFAULT_CONFIG and isinstance(override, dict):
            set_section(session, section, override)
    session.flush()
    return get_all(session)
