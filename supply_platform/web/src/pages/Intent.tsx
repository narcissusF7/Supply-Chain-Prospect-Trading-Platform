import { useCallback, useEffect, useState } from "react";
import { Box, Button, Chip, CircularProgress, Grid, Paper, Stack, Typography } from "@mui/material";
import DataTable, { type Column } from "../components/DataTable";
import { api } from "../api";
import { useNotify } from "../notify";
import type { LeadOut } from "../types";

/**
 * 意向工作台：列出 state=CONTACTED 的线索（可标记意向），
 * 并展示已转为 INTERESTED 的线索列表。
 */
export default function Intent() {
  const { notify } = useNotify();
  const [contacted, setContacted] = useState<LeadOut[]>([]);
  const [interested, setInterested] = useState<LeadOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [c, i] = await Promise.all([
        api.listLeads({ state: "CONTACTED" }),
        api.listLeads({ state: "INTERESTED" }),
      ]);
      setContacted(c);
      setInterested(i);
    } catch (err) {
      notify(err instanceof Error ? err.message : "加载失败", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

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

  const contactedColumns: Column<LeadOut>[] = [
    { id: "name", label: "姓名" },
    { id: "company", label: "公司" },
    { id: "phone", label: "电话" },
    { id: "tier", label: "分层", align: "center", render: (r) => r.tier ?? "—" },
    { id: "source", label: "来源" },
    {
      id: "action",
      label: "操作",
      align: "center",
      render: (r) => (
        <Stack direction="row" justifyContent="center">
          <Button
            size="small"
            variant="contained"
            disabled={pending === r.id}
            onClick={() => handleIntent(r.id)}
          >
            {pending === r.id ? "处理中" : "标记意向"}
          </Button>
        </Stack>
      ),
    },
  ];

  const interestedColumns: Column<LeadOut>[] = [
    { id: "name", label: "姓名" },
    { id: "company", label: "公司" },
    { id: "phone", label: "电话" },
    { id: "tier", label: "分层", align: "center", render: (r) => r.tier ?? "—" },
    { id: "score", label: "评分", align: "center" },
    { id: "source", label: "来源" },
  ];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        意向工作台
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        处理 CONTACTED 线索并标记意向（CONTACTED → INTERESTED），同时查看已意向线索。
      </Typography>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={3}>
          <Grid item xs={12} lg={7}>
            <Paper variant="outlined" sx={{ p: 2, mb: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Chip label="CONTACTED" size="small" color="secondary" />
                <Typography variant="subtitle2">待处理（{contacted.length}）</Typography>
              </Stack>
            </Paper>
            <DataTable
              columns={contactedColumns}
              rows={contacted}
              rowKey={(r) => r.id}
              emptyText="暂无 CONTACTED 线索"
            />
          </Grid>
          <Grid item xs={12} lg={5}>
            <Paper variant="outlined" sx={{ p: 2, mb: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Chip label="INTERESTED" size="small" color="success" />
                <Typography variant="subtitle2">已意向（{interested.length}）</Typography>
              </Stack>
            </Paper>
            <DataTable
              columns={interestedColumns}
              rows={interested}
              rowKey={(r) => r.id}
              emptyText="暂无 INTERESTED 线索"
            />
          </Grid>
        </Grid>
      )}
    </Box>
  );
}
