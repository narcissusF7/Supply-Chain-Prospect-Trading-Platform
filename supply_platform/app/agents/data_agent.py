"""Data Agent（数据采集智能体）。

职责边界（独立模块，体现"隔离会话"设计意图）：
- collect:   从 mock 第三方 API（内置种子/本地 JSON）拉取商户数据
- normalize: 统一字段、生成去重主键 unified_key
- score:     确定性规则打分 + 分层（预留 LLM 评分扩展点）
- ingest:    CRM 入库 + 按 unified_key 去重合并
- score_lead / score_all: 对 NEW 线索执行评分分层 → SCORED

扩展点：
- 第三方 API 适配：实现一个返回与 BUILTIN 同构列表的函数即可替换数据源。
- LLM 评分：score() 中标注 "此处未来接 LLM 推理"。
"""
from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config_store import DEFAULT_CONFIG, get_section, get_scoring_config
from app.state_machine import LeadState, transition

logger = logging.getLogger("supply.data_agent")

# 内置种子（模拟第三方 API 返回的商户数据）
BUILTIN_MERCHANTS: list[dict] = [
    {"name": "张伟", "company": "北京云帆科技有限公司",
     "credit_code": "91110108MA01ABC01X", "phone": "13800000001",
     "region": "beijing", "employees": 320, "pilp_consent": True, "source": "api_mock"},
    {"name": "李娜", "company": "上海浦江贸易有限公司",
     "credit_code": "91310115MA01DEF02Y", "phone": "13800000002",
     "region": "shanghai", "employees": 45, "pilp_consent": True, "source": "api_mock"},
    {"name": "王强", "company": "广州天河商贸行",
     "credit_code": "91440101MA01GHI03Z", "phone": "13800000003",
     "region": "guangzhou", "employees": 12, "pilp_consent": False, "source": "api_mock"},
    {"name": "赵敏", "company": "深圳前海数据服务有限公司",
     "credit_code": "91440300MA01JKL04A", "phone": "13800000004",
     "region": "shenzhen", "employees": 150, "pilp_consent": True, "source": "api_mock"},
    {"name": "陈晨", "company": "杭州西湖网络科技",
     "credit_code": None, "phone": "13800000005",
     "region": "hangzhou", "employees": 8, "pilp_consent": True, "source": "api_mock"},
]


def fetch_from_api() -> list[dict]:
    """模拟第三方 API 拉取。

    扩展点：未来替换为 requests.get(<third_party_url>).json()，
    只要返回结构与 BUILTIN_MERCHANTS 同构即可无缝替换。
    """
    # 此处可改为：return requests.get(API_URL).json()
    return list(BUILTIN_MERCHANTS)


def normalize(raw: dict) -> dict:
    """归一化单条原始数据，生成统一主键 unified_key。

    去重主键优先使用统一社会信用代码，缺失则用手机号。
    """
    credit_code = (raw.get("credit_code") or "").strip() or None
    phone = (raw.get("phone") or "").strip() or None
    unified_key = credit_code or phone
    if unified_key is None:
        raise ValueError(f"缺少信用代码与手机号，无法生成主键：{raw}")
    return {
        "unified_key": unified_key,
        "name": raw.get("name", ""),
        "company": raw.get("company", ""),
        "credit_code": credit_code,
        "phone": phone,
        "region": raw.get("region", "other"),
        "employees": int(raw.get("employees", 0) or 0),
        "pilp_consent": bool(raw.get("pilp_consent", False)),
        "source": raw.get("source", "api_mock"),
    }


def score(normalized: dict, cfg: dict | None = None) -> tuple[int, str]:
    """确定性规则评分 → (score, tier)。

    权重与阈值从评分配置 cfg 读取（默认取 DEFAULT_CONFIG["scoring"]），
    使「系统设置 → 评分配置」可视化编辑真正生效；无 cfg 时回退默认值。

    规则（默认总分 100，全部数值可在配置中调整）：
    - 有统一社会信用代码 +credit_code_points
    - 员工规模：>=emp_threshold_high +emp_high_points,
                 >=emp_threshold_mid +emp_mid_points, 否则 +emp_low_points
    - 区域：命中 tier1_regions +region_tier1_points，否则 +region_other_points
    - 已获 PIPL 同意 +pilp_points
    分层：>=tier_a_min 为 A，>=tier_b_min 为 B，否则 C

    扩展点：此处未来接 LLM 推理/多因子模型，替换下方规则即可。
    """
    if cfg is None:
        cfg = DEFAULT_CONFIG["scoring"]

    s = 0
    if normalized.get("credit_code"):
        s += int(cfg["credit_code_points"])
    emp = int(normalized.get("employees", 0) or 0)
    if emp >= int(cfg["emp_threshold_high"]):
        s += int(cfg["emp_high_points"])
    elif emp >= int(cfg["emp_threshold_mid"]):
        s += int(cfg["emp_mid_points"])
    else:
        s += int(cfg["emp_low_points"])

    tier1 = set(cfg.get("tier1_regions") or [])
    if normalized.get("region") in tier1:
        s += int(cfg["region_tier1_points"])
    else:
        s += int(cfg["region_other_points"])
    if normalized.get("pilp_consent"):
        s += int(cfg["pilp_points"])

    # 扩展点：未来在此调用 LLM 进行语义评分并对 s 做加权修正
    if s >= int(cfg["tier_a_min"]):
        tier = "A"
    elif s >= int(cfg["tier_b_min"]):
        tier = "B"
    else:
        tier = "C"
    return s, tier


def ingest(session: Session, raw_list: list[dict]) -> list[models.Lead]:
    """入库 + 去重合并。

    按 unified_key 去重：已存在则跳过（保持既有评分/状态），不存在则新建并初始化状态 NEW。
    """
    created: list[models.Lead] = []
    for raw in raw_list:
        n = normalize(raw)
        existing = session.execute(
            select(models.Lead).where(models.Lead.unified_key == n["unified_key"])
        ).scalars().first()
        if existing is not None:
            # 去重合并：已存在则跳过（幂等 seed）；真实场景可在此合并字段
            logger.info("去重：线索已存在 unified_key=%s，跳过", n["unified_key"])
            continue
        lead = models.Lead(
            unified_key=n["unified_key"],
            name=n["name"],
            company=n["company"],
            credit_code=n["credit_code"],
            phone=n["phone"],
            source=n["source"],
            region=n["region"],
            employees=n["employees"],
            pilp_consent=n["pilp_consent"],
            # score/tier 初始为空，待 /score 阶段计算
        )
        session.add(lead)
        session.flush()  # 拿到 lead.id
        # 初始化状态机单一事实源
        session.add(models.LeadState(lead_id=lead.id, state=LeadState.NEW.value))
        created.append(lead)
        logger.info("新增线索 unified_key=%s", n["unified_key"])
    session.commit()
    return created


def collect(session: Session, source: str | None = None) -> list[models.Lead]:
    """采集主流程：拉取 → 按采集配置过滤 → 入库。返回本次新增的线索。

    过滤规则从「系统设置 → 采集配置」读取：
    - source：仅采集该数据源（None 或不传则用配置 source；显式参数优先）
    - min_employees：员工规模低于阈值的商户跳过
    - allowed_regions：非空时仅保留这些区域
    """
    cfg = get_section(session, "collection")
    cfg_source = source if source is not None else cfg.get("source") or None
    min_employees = int(cfg.get("min_employees", 0) or 0)
    allowed_regions = set(cfg.get("allowed_regions") or [])
    batch_size = int(cfg.get("batch_size", 0) or 0)

    raw = fetch_from_api()
    if cfg_source:
        raw = [r for r in raw if r.get("source") == cfg_source]
    if min_employees > 0:
        raw = [r for r in raw if int(r.get("employees", 0) or 0) >= min_employees]
    if allowed_regions:
        raw = [r for r in raw if r.get("region") in allowed_regions]
    if batch_size > 0:
        raw = raw[:batch_size]
    return ingest(session, raw)


def _lead_to_raw(lead: models.Lead) -> dict:
    """从 Lead 还原评分所需原始字段（含 region/employees）。"""
    return {
        "name": lead.name,
        "company": lead.company,
        "credit_code": lead.credit_code,
        "phone": lead.phone,
        "region": lead.region,
        "employees": lead.employees,
        "pilp_consent": lead.pilp_consent,
        "source": lead.source,
    }


def score_lead(session: Session, lead_id: int) -> dict:
    """对单一 NEW 线索评分分层 → SCORED。评分权重/阈值读取评分配置。"""
    lead = session.get(models.Lead, lead_id)
    if lead is None:
        return {"ok": False, "reason": "线索不存在"}
    n = normalize(_lead_to_raw(lead))
    cfg = get_scoring_config(session)
    s, tier = score(n, cfg)
    lead.score = s
    lead.tier = tier
    result = transition(session, lead_id, LeadState.SCORED, agent="data_agent", audit=True)
    session.commit()
    return {"ok": result.ok, "score": s, "tier": tier, "state_result": result.message}


def score_all(session: Session) -> list[dict]:
    """对全部 NEW 线索评分分层。"""
    stmt = (
        select(models.Lead)
        .join(models.LeadState, models.Lead.id == models.LeadState.lead_id)
        .where(models.LeadState.state == LeadState.NEW.value)
    )
    results: list[dict] = []
    for lead in session.execute(stmt).scalars().all():
        results.append(score_lead(session, lead.id))
    return results
