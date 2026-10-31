import { useCallback, useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  FormControlLabel,
  Grid,
  Paper,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { api } from "../api";
import { useNotify } from "../notify";
import type { ConfigValue, SettingsOut } from "../types";

/** 字段类型：number / text / switch / array（逗号分隔字符串）。 */
type FieldType = "number" | "text" | "switch" | "array";

interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  helper?: string;
  min?: number;
  max?: number;
}

interface SectionMeta {
  key: keyof SettingsOut;
  label: string;
  fields: FieldDef[];
}

/** 三个配置段的可视化字段定义（与后端 DEFAULT_CONFIG 字段一一对应）。 */
const SECTIONS: SectionMeta[] = [
  {
    key: "collection",
    label: "采集配置",
    fields: [
      { key: "source", label: "数据源标识", type: "text", helper: "如 api_mock；未来接第三方 API 名" },
      { key: "min_employees", label: "员工规模下限", type: "number", min: 0, helper: "低于此规模的商家不采集（0 = 不过滤）" },
      { key: "batch_size", label: "单次采集上限", type: "number", min: 0, helper: "单次采集最大条数（0 = 不限制）" },
      { key: "allowed_regions", label: "允许采集区域", type: "array", helper: "逗号分隔，如 beijing,shanghai；留空 = 全部" },
    ],
  },
  {
    key: "scoring",
    label: "评分配置",
    fields: [
      { key: "credit_code_points", label: "信用代码加分", type: "number", min: 0 },
      { key: "emp_threshold_high", label: "员工「高」阈值", type: "number", min: 0, helper: ">= 取高规模加分" },
      { key: "emp_high_points", label: "高规模加分", type: "number", min: 0 },
      { key: "emp_threshold_mid", label: "员工「中」阈值", type: "number", min: 0, helper: ">= 取中规模加分，否则小规模" },
      { key: "emp_mid_points", label: "中规模加分", type: "number", min: 0 },
      { key: "emp_low_points", label: "小规模加分", type: "number", min: 0 },
      { key: "region_tier1_points", label: "一线区域加分", type: "number", min: 0 },
      { key: "region_other_points", label: "其他区域加分", type: "number", min: 0 },
      { key: "tier1_regions", label: "一线区域列表", type: "array", helper: "逗号分隔" },
      { key: "pilp_points", label: "PIPL 同意加分", type: "number", min: 0 },
      { key: "tier_a_min", label: "A 级阈值", type: "number", min: 0, helper: "评分 >= 该值判为 A" },
      { key: "tier_b_min", label: "B 级阈值", type: "number", min: 0, helper: "评分 >= 该值判为 B，否则 C" },
    ],
  },
  {
    key: "compliance",
    label: "合规配置",
    fields: [
      { key: "require_pilp_consent", label: "强制 PIPL 同意", type: "switch", helper: "关闭后将允许触达未同意用户（谨慎）" },
      { key: "enforce_call_window", label: "强制呼叫时段", type: "switch", helper: "外呼仅在时段内允许" },
      { key: "call_start_hour", label: "呼叫起始小时", type: "number", min: 0, max: 23 },
      { key: "call_end_hour", label: "呼叫结束小时", type: "number", min: 0, max: 23 },
      { key: "frequency_window_days", label: "频次窗口(天)", type: "number", min: 1 },
      { key: "frequency_cap", label: "频次上限(次)", type: "number", min: 1, helper: "窗口内最大触达次数" },
    ],
  },
];

/** 把数组字段的展示值（字符串）转回数组，数值/布尔做类型规整。 */
function toPayload(meta: SectionMeta, section: Record<string, ConfigValue>): Record<string, ConfigValue> {
  const out: Record<string, ConfigValue> = {};
  for (const f of meta.fields) {
    const raw = section[f.key];
    if (f.type === "array") {
      const str = typeof raw === "string" ? raw : Array.isArray(raw) ? raw.join(", ") : "";
      out[f.key] = str
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
    } else if (f.type === "number") {
      const n = Number(raw);
      out[f.key] = Number.isFinite(n) ? n : (f.min ?? 0);
    } else if (f.type === "switch") {
      out[f.key] = Boolean(raw);
    } else {
      out[f.key] = String(raw ?? "");
    }
  }
  return out;
}

/** 把数组值渲染为可编辑的字符串。 */
function displayValue(v: ConfigValue): string {
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

/**
 * 系统设置：采集 / 评分 / 合规 可视化配置。
 * 读取 GET /settings，按段编辑保存（PUT /settings 仅传对应段）。
 */
export default function Settings() {
  const { notify } = useNotify();
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  const [draft, setDraft] = useState<SettingsOut | null>(null);
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [savingSection, setSavingSection] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getSettings();
      setSettings(data);
      setDraft(data);
    } catch (err) {
      notify(err instanceof Error ? err.message : "加载配置失败", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleFieldChange = (sectionKey: keyof SettingsOut, field: string, value: ConfigValue) => {
    setDraft((prev) =>
      prev
        ? { ...prev, [sectionKey]: { ...prev[sectionKey], [field]: value } }
        : prev,
    );
  };

  const handleSave = async (meta: SectionMeta) => {
    if (draft == null) return;
    setSavingSection(meta.key);
    try {
      const payload = toPayload(meta, draft[meta.key]);
      const updated = await api.updateSettings({ [meta.key]: payload } as never);
      setSettings(updated);
      setDraft(updated);
      notify(`${meta.label}已保存并生效`, "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : "保存失败", "error");
    } finally {
      setSavingSection(null);
    }
  };

  const sectionMeta = SECTIONS[tab];
  const sectionValues = draft ? draft[sectionMeta.key] : {};

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        系统设置
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        采集 / 评分 / 合规 的可视化配置。保存后立即对采集过滤、评分分层与触达合规校验生效。
      </Typography>

      {loading || draft == null ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Tabs value={tab} onChange={(_e, v) => setTab(v)} sx={{ mb: 2 }} variant="fullWidth">
            {SECTIONS.map((s) => (
              <Tab key={s.key} label={s.label} />
            ))}
          </Tabs>
          <Divider sx={{ mb: 2 }} />

          <Grid container spacing={2}>
            {sectionMeta.fields.map((f) => (
              <Grid item xs={12} sm={6} key={f.key}>
                {f.type === "switch" ? (
                  <FormControlLabel
                    control={
                      <Switch
                        checked={Boolean(sectionValues[f.key])}
                        onChange={(e) => handleFieldChange(sectionMeta.key, f.key, e.target.checked)}
                      />
                    }
                    label={f.label}
                  />
                ) : (
                  <TextField
                    label={f.label}
                    type={f.type === "number" ? "number" : "text"}
                    fullWidth
                    size="small"
                    multiline={f.type === "array"}
                    minRows={f.type === "array" ? 2 : undefined}
                    value={displayValue(sectionValues[f.key])}
                    helperText={f.helper}
                    inputProps={f.type === "number" ? { min: f.min, max: f.max } : undefined}
                    onChange={(e) =>
                      handleFieldChange(
                        sectionMeta.key,
                        f.key,
                        f.type === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value,
                      )
                    }
                  />
                )}
                {f.type === "switch" && f.helper && (
                  <Typography variant="caption" color="text.secondary" display="block">
                    {f.helper}
                  </Typography>
                )}
              </Grid>
            ))}
          </Grid>

          <Stack direction="row" justifyContent="flex-end" sx={{ mt: 3 }}>
            <Button
              variant="contained"
              disabled={savingSection === sectionMeta.key}
              onClick={() => handleSave(sectionMeta)}
            >
              {savingSection === sectionMeta.key ? "保存中" : `保存${sectionMeta.label}`}
            </Button>
          </Stack>
        </Paper>
      )}

      {/* 配置摘要：展示当前生效值，便于核对 */}
      {settings && (
        <Paper variant="outlined" sx={{ p: 2, mt: 3 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Typography variant="subtitle2">当前生效配置</Typography>
            <Chip size="small" label="实时" color="success" />
          </Stack>
          <Grid container spacing={1}>
            {SECTIONS.map((s) => (
              <Grid item xs={12} md={4} key={s.key}>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  {s.label}
                </Typography>
                <Box component="ul" sx={{ m: 0, pl: 2 }}>
                  {s.fields.slice(0, 4).map((f) => (
                    <li key={f.key}>
                      <Typography variant="caption" color="text.secondary">
                        {f.label}: {displayValue(settings[s.key][f.key])}
                      </Typography>
                    </li>
                  ))}
                </Box>
              </Grid>
            ))}
          </Grid>
        </Paper>
      )}
    </Box>
  );
}
