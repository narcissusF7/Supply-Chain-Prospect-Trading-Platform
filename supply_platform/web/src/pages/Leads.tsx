import { useCallback, useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import DataTable, { type Column } from "../components/DataTable";
import { api } from "../api";
import { useNotify } from "../notify";
import { LEAD_STATES, LEAD_TIERS, type LeadOut } from "../types";

/** 状态 → Chip 颜色映射（MUI Chip color 联合类型）。 */
const STATE_COLOR: Record<string, "default" | "primary" | "secondary" | "success" | "warning" | "info" | "error"> = {
  NEW: "default",
  SCORED: "info",
  CONTACTED: "secondary",
  INTERESTED: "success",
  SIGNED: "warning",
  SHIPPED: "error",
};

/**
 * 线索池：GET /leads（支持 state / tier 筛选下拉）；
 * 行内可触发“标记意向”(POST /leads/{id}/intent)，仅当 state=CONTACTED 可用。
 */
export default function Leads() {
  const { notify } = useNotify();
  const [state, setState] = useState<string>("");
  const [tier, setTier] = useState<string>("");
  const [rows, setRows] = useState<LeadOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listLeads({
        state: state || undefined,
        tier: tier || undefined,
      });
      setRows(data);
    } catch (err) {
      notify(err instanceof Error ? err.message : "加载失败", "error");
    } finally {
      setLoading(false);
    }
  }, [state, tier, notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleIntent = async (id: number) => {
    setPending(id);
    try {
      const res = await api.markIntent(id);
      notify(res.detail || (res.ok ? "已标记意向" : "操作失败"), res.ok ? "success" : "error");
      await load();
    } catch (err) {
      notify(err instanceof Error ? err.message : "操作失败", "error");
    } finally {
      setPending(null);
    }
  };

  const columns: Column<LeadOut>[] = [
    { id: "name", label: "姓名" },
    { id: "company", label: "公司" },
    { id: "phone", label: "电话" },
    {
      id: "tier",
      label: "分层",
      align: "center",
      render: (r) =>
        r.tier ? (
          <Chip
            size="small"
            label={r.tier}
            color={r.tier === "A" ? "warning" : r.tier === "B" ? "info" : "default"}
          />
        ) : (
          <Typography variant="caption" color="text.disabled">
            —
          </Typography>
        ),
    },
    { id: "score", label: "评分", align: "center" },
    {
      id: "state",
      label: "状态",
      align: "center",
      render: (r) => <Chip size="small" label={r.state} color={STATE_COLOR[r.state] ?? "default"} />,
    },
    {
      id: "pilp_consent",
      label: "PIPL",
      align: "center",
      render: (r) => (
        <Chip
          size="small"
          variant="outlined"
          label={r.pilp_consent ? "已同意" : "未同意"}
          color={r.pilp_consent ? "success" : "error"}
        />
      ),
    },
    { id: "source", label: "来源" },
    {
      id: "created_at",
      label: "创建时间",
      render: (r) => new Date(r.created_at).toLocaleString("zh-CN"),
    },
    {
      id: "action",
      label: "操作",
      align: "center",
      render: (r) => (
        <Button
          size="small"
          variant="outlined"
          disabled={r.state !== "CONTACTED" || pending === r.id}
          onClick={() => handleIntent(r.id)}
        >
          {pending === r.id ? "处理中" : "标记意向"}
        </Button>
      ),
    },
  ];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        线索池
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        全部线索列表，可按状态 / 分层筛选；CONTACTED 状态可标记意向。
      </Typography>

      <Stack
        direction="row"
        spacing={2}
        flexWrap="wrap"
        useFlexGap
        sx={{ mb: 2 }}
        alignItems="center"
      >
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="filter-state-label">状态</InputLabel>
          <Select
            labelId="filter-state-label"
            label="状态"
            value={state}
            onChange={(e) => setState(e.target.value)}
          >
            <MenuItem value="">全部</MenuItem>
            {LEAD_STATES.map((s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel id="filter-tier-label">分层</InputLabel>
          <Select
            labelId="filter-tier-label"
            label="分层"
            value={tier}
            onChange={(e) => setTier(e.target.value)}
          >
            <MenuItem value="">全部</MenuItem>
            {LEAD_TIERS.map((t) => (
              <MenuItem key={t} value={t}>
                {t}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {loading && <CircularProgress size={20} />}
      </Stack>

      <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} emptyText="暂无线索，请先执行采集" />
    </Box>
  );
}
