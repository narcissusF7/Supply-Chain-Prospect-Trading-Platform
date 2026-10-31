import { useEffect, useState } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import DataTable, { type Column } from "../components/DataTable";
import { api } from "../api";
import { useNotify } from "../notify";
import type { AuditOut } from "../types";

/**
 * 审计日志：GET /audit 表格展示 event_type / lead_id / agent / detail / created_at。
 */
export default function Audit() {
  const { notify } = useNotify();
  const [rows, setRows] = useState<AuditOut[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await api.listAudit();
        setRows(data);
      } catch (err) {
        notify(err instanceof Error ? err.message : "加载失败", "error");
      } finally {
        setLoading(false);
      }
    })();
  }, [notify]);

  const columns: Column<AuditOut>[] = [
    { id: "event_type", label: "事件类型" },
    { id: "lead_id", label: "线索ID", align: "center", render: (r) => r.lead_id ?? "—" },
    { id: "agent", label: "智能体", render: (r) => r.agent ?? "—" },
    { id: "detail", label: "详情" },
    {
      id: "created_at",
      label: "时间",
      render: (r) => new Date(r.created_at).toLocaleString("zh-CN"),
    },
  ];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        审计日志
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        所有触达 / 合规 / 状态变更留痕（按时间倒序）。
      </Typography>
      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <DataTable columns={columns} rows={rows} rowKey={(r) => r.id} emptyText="暂无审计记录" />
      )}
    </Box>
  );
}
