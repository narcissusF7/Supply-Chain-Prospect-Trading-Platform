import { useEffect, useMemo, useState } from "react";
import {
  Box,
  CircularProgress,
  Grid,
  Paper,
  Typography,
} from "@mui/material";
import PeopleAltIcon from "@mui/icons-material/PeopleAlt";
import StarIcon from "@mui/icons-material/Star";
import FlagIcon from "@mui/icons-material/Flag";
import StatCard from "../components/StatCard";
import StateFunnel from "../components/StateFunnel";
import ActionPanel from "../components/ActionPanel";
import { api } from "../api";
import { useNotify } from "../notify";
import type { AuditOut, LeadOut } from "../types";

/**
 * 仪表盘：调用 GET /leads 与 GET /audit 在客户端做统计，
 * 用 StatCard + StateFunnel 展示；并提供一键流水线按钮。
 */
export default function Dashboard() {
  const { notify } = useNotify();
  const [leads, setLeads] = useState<LeadOut[]>([]);
  const [audits, setAudits] = useState<AuditOut[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [l, a] = await Promise.all([api.listLeads(), api.listAudit()]);
      setLeads(l);
      setAudits(a);
    } catch (err) {
      notify(err instanceof Error ? err.message : "数据加载失败", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const stats = useMemo(() => {
    const stateCounts: Record<string, number> = {};
    const tierCounts: Record<string, number> = { A: 0, B: 0, C: 0 };
    for (const lead of leads) {
      stateCounts[lead.state] = (stateCounts[lead.state] ?? 0) + 1;
      if (lead.tier) tierCounts[lead.tier] = (tierCounts[lead.tier] ?? 0) + 1;
    }
    return { stateCounts, tierCounts };
  }, [leads]);

  const actions = [
    { label: "种子数据", color: "secondary" as const, onClick: () => api.seed() },
    { label: "采集线索", color: "info" as const, onClick: () => api.collect() },
    { label: "评分分层", color: "primary" as const, onClick: () => api.score() },
    { label: "触达(SMS)", color: "warning" as const, onClick: () => api.outreach("SMS") },
  ];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        仪表盘
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        平台线索全生命周期概览（数据由 GET /leads 与 GET /audit 实时拉取）。
      </Typography>

      <ActionPanel
        title="一键流水线"
        buttons={actions}
        note="依次执行 种子(seed) → 采集(collect) → 评分(score) → 触达(outreach)，每一步调用对应后端接口并显示返回 detail。"
        busyLabel="执行中..."
      />

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={3}>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="线索总数" value={leads.length} icon={<PeopleAltIcon />} />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="A 级线索" value={stats.tierCounts.A} color="#f59e0b" icon={<StarIcon />} />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="B 级线索" value={stats.tierCounts.B} color="#3b82f6" icon={<StarIcon />} />
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <StatCard title="C 级线索" value={stats.tierCounts.C} color="#64748b" icon={<StarIcon />} />
          </Grid>

          <Grid item xs={12} md={8}>
            <Paper variant="outlined" sx={{ p: 3, height: "100%" }}>
              <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                阶段漏斗
              </Typography>
              <StateFunnel counts={stats.stateCounts} />
            </Paper>
          </Grid>

          <Grid item xs={12} md={4}>
            <Paper variant="outlined" sx={{ p: 3, height: "100%" }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
                <FlagIcon color="action" />
                <Typography variant="subtitle1" fontWeight={600}>
                  审计事件
                </Typography>
              </Box>
              <Typography variant="h3" fontWeight={700}>
                {audits.length}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                累计记录（触达 / 合规 / 状态变更）
              </Typography>
            </Paper>
          </Grid>
        </Grid>
      )}
    </Box>
  );
}
