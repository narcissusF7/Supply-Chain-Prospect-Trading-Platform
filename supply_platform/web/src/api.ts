/**
 * API 封装模块。
 * - 统一基础路径 `/api/v1`（dev 下由 Vite 代理转发到 http://localhost:8000）。
 * - 统一 fetch 封装 GET / POST，自动处理 JSON 与错误。
 * - 不修改后端；仅消费已有接口。
 */
import type {
  AuditOut,
  ContractOut,
  FulfillmentOrderOut,
  GenericOut,
  HealthOut,
  LeadOut,
  SettingsOut,
  SettingsUpdate,
  ShipRequest,
  SignRequest,
  TrackingResult,
} from "./types";

const BASE = "/api/v1";

/**
 * 通用请求封装：处理 JSON 解析、HTTP 错误与后端 detail 提取。
 */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const message =
      data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : `HTTP ${res.status} ${res.statusText}`;
    throw new Error(message);
  }

  return data as T;
}

export interface ListLeadsParams {
  state?: string;
  tier?: string;
}

export const api = {
  /** GET /health → { status } */
  health: () => request<HealthOut>("/health"),

  /** POST /seed → { ok, detail } */
  seed: () => request<GenericOut>("/seed", { method: "POST" }),

  /** POST /collect → { ok, detail } */
  collect: () => request<GenericOut>("/collect", { method: "POST" }),

  /** POST /score → { ok, detail } */
  score: () => request<GenericOut>("/score", { method: "POST" }),

  /** POST /outreach?channel=SMS → { ok, detail }（内部必过合规） */
  outreach: (channel = "SMS") =>
    request<GenericOut>(
      `/outreach?channel=${encodeURIComponent(channel)}`,
      { method: "POST" },
    ),

  /** GET /leads?state=&tier= → LeadOut[] */
  listLeads: (params: ListLeadsParams = {}) => {
    const qs = new URLSearchParams();
    if (params.state) qs.set("state", params.state);
    if (params.tier) qs.set("tier", params.tier);
    const query = qs.toString();
    return request<LeadOut[]>(`/leads${query ? `?${query}` : ""}`);
  },

  /** POST /leads/{lead_id}/intent → { ok, detail } */
  markIntent: (leadId: number) =>
    request<GenericOut>(`/leads/${leadId}/intent`, { method: "POST" }),

  /** GET /audit → AuditOut[] */
  listAudit: () => request<AuditOut[]>("/audit"),

  /** POST /dispatch/{lead_id} → { ok, detail }（按状态派活演示） */
  dispatch: (leadId: number) =>
    request<GenericOut>(`/dispatch/${leadId}`, { method: "POST" }),

  /** POST /leads/{lead_id}/sign → { ok, detail }（签约：INTERESTED → SIGNED） */
  sign: (leadId: number, body: SignRequest) =>
    request<GenericOut>(`/leads/${leadId}/sign`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** POST /leads/{lead_id}/ship → { ok, detail }（发货：SIGNED → SHIPPED） */
  ship: (leadId: number, body: ShipRequest) =>
    request<GenericOut>(`/leads/${leadId}/ship`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** GET /contracts → ContractOut[]（按 id 倒序） */
  listContracts: () => request<ContractOut[]>("/contracts"),

  /** GET /orders → FulfillmentOrderOut[]（按 id 倒序） */
  listOrders: () => request<FulfillmentOrderOut[]>("/orders"),

  /** GET /leads/{lead_id}/tracking → TrackingResult（该 lead 最新物流轨迹） */
  getTracking: (leadId: number) =>
    request<TrackingResult>(`/leads/${leadId}/tracking`),

  /** GET /settings → SettingsOut（全量采集/评分/合规配置） */
  getSettings: () => request<SettingsOut>("/settings"),

  /** PUT /settings → SettingsOut（按段部分更新，body 为 SettingsUpdate） */
  updateSettings: (body: SettingsUpdate) =>
    request<SettingsOut>("/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};

export default api;
