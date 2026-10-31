/**
 * 后端 API 数据契约类型（与 app/schemas.py 对齐，请勿臆造字段）。
 * created_at 为 ISO 字符串（前端无需本地时区重算，直接展示）。
 */

export interface HealthOut {
  status: string;
}

export interface GenericOut {
  ok: boolean;
  detail: string;
}

export interface LeadOut {
  id: number;
  unified_key: string;
  name: string;
  company: string;
  credit_code: string | null;
  phone: string | null;
  source: string;
  tier: string | null;
  score: number | null;
  pilp_consent: boolean;
  state: string;
  created_at: string;
}

export interface AuditOut {
  id: number;
  event_type: string;
  lead_id: number | null;
  agent: string | null;
  detail: string;
  created_at: string;
}

/** 电子签约合同（与后端 ContractOut 对齐）。 */
export interface ContractOut {
  id: number;
  lead_id: number;
  contract_no: string;
  signer_name: string | null;
  signer_phone: string | null;
  contract_url: string;
  provider: string;
  status: string;
  created_at: string;
  signed_at: string | null;
}

/** 履约发货单（与后端 FulfillmentOrderOut 对齐）。 */
export interface FulfillmentOrderOut {
  id: number;
  lead_id: number;
  contract_id: number | null;
  sku: string;
  qty: number;
  receiver_name: string | null;
  receiver_phone: string | null;
  receiver_address: string | null;
  tracking_no: string | null;
  logistics_provider: string;
  status: string;
  created_at: string;
  shipped_at: string | null;
}

/** 物流轨迹单条节点。 */
export interface TrackingTrace {
  time: string;
  desc: string;
}

/** 物流轨迹查询结果（成功形态）；无物流单时返回 { ok: false; reason }。 */
export type TrackingResult =
  | {
      provider: string;
      status: string;
      tracking_no: string;
      traces: TrackingTrace[];
    }
  | { ok: false; reason: string };

/** 发起签约请求体。 */
export interface SignRequest {
  signer_name: string;
  signer_phone: string;
}

/** 安排发货请求体。 */
export interface ShipRequest {
  sku: string;
  qty: number;
  receiver_name: string;
  receiver_phone: string;
  receiver_address: string;
}

/** 线索状态机：NEW → SCORED → CONTACTED → INTERESTED → SIGNED → SHIPPED */
export const LEAD_STATES = [
  "NEW",
  "SCORED",
  "CONTACTED",
  "INTERESTED",
  "SIGNED",
  "SHIPPED",
] as const;
export type LeadState = (typeof LEAD_STATES)[number];

/** 评分分层 */
export const LEAD_TIERS = ["A", "B", "C"] as const;
export type LeadTier = (typeof LEAD_TIERS)[number];

/** 系统设置（采集 / 评分 / 合规 配置值，支持数值 / 字符串 / 布尔 / 字符串数组）。 */
export type ConfigValue = number | string | boolean | string[];
export interface SettingsOut {
  collection: Record<string, ConfigValue>;
  scoring: Record<string, ConfigValue>;
  compliance: Record<string, ConfigValue>;
}
export interface SettingsUpdate {
  collection?: Record<string, ConfigValue>;
  scoring?: Record<string, ConfigValue>;
  compliance?: Record<string, ConfigValue>;
}
