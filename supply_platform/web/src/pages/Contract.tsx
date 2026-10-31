import { useCallback, useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Link,
  List,
  ListItem,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import DataTable, { type Column } from "../components/DataTable";
import { api } from "../api";
import { useNotify } from "../notify";
import type {
  ContractOut,
  FulfillmentOrderOut,
  LeadOut,
  ShipRequest,
  SignRequest,
  TrackingResult,
} from "../types";

/** 线索状态 → Chip 颜色（沿用 Leads 页思路：SIGNED 黄、SHIPPED 红）。 */
const LEAD_STATE_COLOR: Record<
  string,
  "default" | "primary" | "secondary" | "success" | "warning" | "info" | "error"
> = {
  NEW: "default",
  SCORED: "info",
  CONTACTED: "secondary",
  INTERESTED: "success",
  SIGNED: "warning",
  SHIPPED: "error",
};

/** 合同状态 → Chip 颜色。 */
const CONTRACT_STATUS_COLOR: Record<string, "default" | "success" | "warning"> = {
  PENDING: "warning",
  SIGNED: "success",
};

/** 履约单状态 → Chip 颜色（SHIPPED 红、DELIVERED 绿、CREATED 灰）。 */
const ORDER_STATUS_COLOR: Record<string, "default" | "success" | "warning" | "error"> = {
  CREATED: "default",
  SHIPPED: "error",
  DELIVERED: "success",
};

interface SignDialogState {
  open: boolean;
  leadId: number | null;
  signer_name: string;
  signer_phone: string;
}

interface ShipDialogState {
  open: boolean;
  leadId: number | null;
  sku: string;
  qty: string;
  receiver_name: string;
  receiver_phone: string;
  receiver_address: string;
}

interface TrackingDialogState {
  open: boolean;
  leadId: number | null;
  result: TrackingResult | null;
}

const EMPTY_SIGN: SignDialogState = {
  open: false,
  leadId: null,
  signer_name: "",
  signer_phone: "",
};

const EMPTY_SHIP: ShipDialogState = {
  open: false,
  leadId: null,
  sku: "DEFAULT",
  qty: "1",
  receiver_name: "",
  receiver_phone: "",
  receiver_address: "",
};

const EMPTY_TRACKING: TrackingDialogState = { open: false, leadId: null, result: null };

/**
 * 签约履约工作台：
 * - 左：待签约（INTERESTED）列表，行内「发起签约」→ Dialog 收集签约人信息（可空）→ 调 sign。
 * - 中：待发货（SIGNED）列表，行内「安排发货」→ Dialog 收集 SKU/数量/收件信息 → 调 ship。
 * - 下：合同列表 + 履约物流列表，含「查看物流」拉取轨迹。
 */
export default function Contract() {
  const { notify } = useNotify();
  const [interested, setInterested] = useState<LeadOut[]>([]);
  const [signed, setSigned] = useState<LeadOut[]>([]);
  const [contracts, setContracts] = useState<ContractOut[]>([]);
  const [orders, setOrders] = useState<FulfillmentOrderOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<number | null>(null);

  const [signDialog, setSignDialog] = useState<SignDialogState>(EMPTY_SIGN);
  const [shipDialog, setShipDialog] = useState<ShipDialogState>(EMPTY_SHIP);
  const [trackingDialog, setTrackingDialog] = useState<TrackingDialogState>(EMPTY_TRACKING);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [intr, sgnd, cts, ords] = await Promise.all([
        api.listLeads({ state: "INTERESTED" }),
        api.listLeads({ state: "SIGNED" }),
        api.listContracts(),
        api.listOrders(),
      ]);
      setInterested(intr);
      setSigned(sgnd);
      setContracts(cts);
      setOrders(ords);
    } catch (err) {
      notify(err instanceof Error ? err.message : "加载失败", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  // ---------------- 签约 ----------------

  const handleSignOpen = (leadId: number) => {
    setSignDialog({ ...EMPTY_SIGN, open: true, leadId });
  };

  const handleSignClose = () => setSignDialog(EMPTY_SIGN);

  const handleSignSubmit = async () => {
    if (signDialog.leadId == null) return;
    const id = signDialog.leadId;
    setPending(id);
    try {
      const body: SignRequest = {
        signer_name: signDialog.signer_name,
        signer_phone: signDialog.signer_phone,
      };
      const res = await api.sign(id, body);
      notify(res.detail || (res.ok ? "签约成功" : "签约失败"), res.ok ? "success" : "error");
      handleSignClose();
      await load();
    } catch (err) {
      notify(err instanceof Error ? err.message : "签约失败", "error");
    } finally {
      setPending(null);
    }
  };

  // ---------------- 发货 ----------------

  const handleShipOpen = (leadId: number) => {
    setShipDialog({ ...EMPTY_SHIP, open: true, leadId });
  };

  const handleShipClose = () => setShipDialog(EMPTY_SHIP);

  const handleShipSubmit = async () => {
    if (shipDialog.leadId == null) return;
    const id = shipDialog.leadId;
    setPending(id);
    try {
      const body: ShipRequest = {
        sku: shipDialog.sku || "DEFAULT",
        qty: parseInt(shipDialog.qty, 10) || 1,
        receiver_name: shipDialog.receiver_name,
        receiver_phone: shipDialog.receiver_phone,
        receiver_address: shipDialog.receiver_address,
      };
      const res = await api.ship(id, body);
      notify(res.detail || (res.ok ? "发货成功" : "发货失败"), res.ok ? "success" : "error");
      handleShipClose();
      await load();
    } catch (err) {
      notify(err instanceof Error ? err.message : "发货失败", "error");
    } finally {
      setPending(null);
    }
  };

  // ---------------- 物流轨迹 ----------------

  const handleTrackingOpen = async (leadId: number) => {
    setPending(leadId);
    try {
      const result = await api.getTracking(leadId);
      setTrackingDialog({ open: true, leadId, result });
    } catch (err) {
      notify(err instanceof Error ? err.message : "查询物流失败", "error");
    } finally {
      setPending(null);
    }
  };

  const handleTrackingClose = () => setTrackingDialog(EMPTY_TRACKING);

  // ---------------- 列定义 ----------------

  const interestedColumns: Column<LeadOut>[] = [
    { id: "name", label: "姓名" },
    { id: "company", label: "公司" },
    { id: "phone", label: "电话" },
    { id: "tier", label: "分层", align: "center", render: (r) => r.tier ?? "—" },
    {
      id: "state",
      label: "状态",
      align: "center",
      render: (r) => (
        <Chip size="small" label={r.state} color={LEAD_STATE_COLOR[r.state] ?? "default"} />
      ),
    },
    {
      id: "action",
      label: "操作",
      align: "center",
      render: (r) => (
        <Button
          size="small"
          variant="contained"
          disabled={pending === r.id}
          onClick={() => handleSignOpen(r.id)}
        >
          {pending === r.id ? "处理中" : "发起签约"}
        </Button>
      ),
    },
  ];

  const signedColumns: Column<LeadOut>[] = [
    { id: "name", label: "姓名" },
    { id: "company", label: "公司" },
    { id: "phone", label: "电话" },
    { id: "tier", label: "分层", align: "center", render: (r) => r.tier ?? "—" },
    {
      id: "state",
      label: "状态",
      align: "center",
      render: (r) => (
        <Chip size="small" label={r.state} color={LEAD_STATE_COLOR[r.state] ?? "default"} />
      ),
    },
    {
      id: "action",
      label: "操作",
      align: "center",
      render: (r) => (
        <Button
          size="small"
          variant="contained"
          color="warning"
          disabled={pending === r.id}
          onClick={() => handleShipOpen(r.id)}
        >
          {pending === r.id ? "处理中" : "安排发货"}
        </Button>
      ),
    },
  ];

  const contractColumns: Column<ContractOut>[] = [
    { id: "contract_no", label: "合同编号" },
    {
      id: "signer",
      label: "签约人",
      render: (c) =>
        c.signer_name || c.signer_phone ? `${c.signer_name ?? ""} ${c.signer_phone ?? ""}`.trim() : "—",
    },
    {
      id: "status",
      label: "状态",
      align: "center",
      render: (c) => (
        <Chip size="small" label={c.status} color={CONTRACT_STATUS_COLOR[c.status] ?? "default"} />
      ),
    },
    { id: "provider", label: "通道", align: "center" },
    {
      id: "contract_url",
      label: "合同链接",
      render: (c) =>
        c.contract_url ? (
          <Link href={c.contract_url} target="_blank" rel="noopener noreferrer">
            查看
          </Link>
        ) : (
          "—"
        ),
    },
    { id: "created_at", label: "创建时间", render: (c) => new Date(c.created_at).toLocaleString("zh-CN") },
  ];

  const orderColumns: Column<FulfillmentOrderOut>[] = [
    { id: "sku", label: "SKU" },
    { id: "qty", label: "数量", align: "center" },
    {
      id: "receiver",
      label: "收件人",
      render: (o) =>
        o.receiver_name || o.receiver_phone ? `${o.receiver_name ?? ""} ${o.receiver_phone ?? ""}`.trim() : "—",
    },
    { id: "tracking_no", label: "物流单号", render: (o) => o.tracking_no ?? "—" },
    { id: "logistics_provider", label: "物流商", align: "center" },
    {
      id: "status",
      label: "状态",
      align: "center",
      render: (o) => (
        <Chip size="small" label={o.status} color={ORDER_STATUS_COLOR[o.status] ?? "default"} />
      ),
    },
    {
      id: "action",
      label: "物流",
      align: "center",
      render: (o) =>
        o.tracking_no ? (
          <Button
            size="small"
            variant="outlined"
            disabled={pending === o.lead_id}
            onClick={() => handleTrackingOpen(o.lead_id)}
          >
            查看物流
          </Button>
        ) : (
          "—"
        ),
    },
    { id: "created_at", label: "创建时间", render: (o) => new Date(o.created_at).toLocaleString("zh-CN") },
  ];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        签约履约
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        对 INTERESTED 线索发起电子签约（法大大 / mock 回退），对 SIGNED 线索安排 WMS 出库与快递鸟物流（mock 回退）；
        无真实凭据时自动走本地 mock，保证可演示。
      </Typography>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={3}>
          <Grid item xs={12} lg={6}>
            <Paper variant="outlined" sx={{ p: 2, mb: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Chip label="INTERESTED" size="small" color="success" />
                <Typography variant="subtitle2">待签约（{interested.length}）</Typography>
              </Stack>
            </Paper>
            <DataTable
              columns={interestedColumns}
              rows={interested}
              rowKey={(r) => r.id}
              emptyText="暂无 INTERESTED 线索"
            />
          </Grid>

          <Grid item xs={12} lg={6}>
            <Paper variant="outlined" sx={{ p: 2, mb: 1 }}>
              <Stack direction="row" alignItems="center" spacing={1}>
                <Chip label="SIGNED" size="small" color="warning" />
                <Typography variant="subtitle2">待发货（{signed.length}）</Typography>
              </Stack>
            </Paper>
            <DataTable
              columns={signedColumns}
              rows={signed}
              rowKey={(r) => r.id}
              emptyText="暂无 SIGNED 线索"
            />
          </Grid>

          <Grid item xs={12} lg={6}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
              合同列表（{contracts.length}）
            </Typography>
            <DataTable
              columns={contractColumns}
              rows={contracts}
              rowKey={(c) => c.id}
              emptyText="暂无合同"
            />
          </Grid>

          <Grid item xs={12} lg={6}>
            <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
              履约物流列表（{orders.length}）
            </Typography>
            <DataTable
              columns={orderColumns}
              rows={orders}
              rowKey={(o) => o.id}
              emptyText="暂无履约单"
            />
          </Grid>
        </Grid>
      )}

      {/* 签约 Dialog */}
      <Dialog open={signDialog.open} onClose={handleSignClose} fullWidth maxWidth="xs">
        <DialogTitle>发起签约</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="签约人姓名"
              size="small"
              fullWidth
              value={signDialog.signer_name}
              onChange={(e) => setSignDialog((s) => ({ ...s, signer_name: e.target.value }))}
              placeholder="可空，默认用线索姓名"
            />
            <TextField
              label="签约人手机号"
              size="small"
              fullWidth
              value={signDialog.signer_phone}
              onChange={(e) => setSignDialog((s) => ({ ...s, signer_phone: e.target.value }))}
              placeholder="可空，默认用线索电话"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleSignClose}>取消</Button>
          <Button variant="contained" onClick={handleSignSubmit}>
            确认签约
          </Button>
        </DialogActions>
      </Dialog>

      {/* 发货 Dialog */}
      <Dialog open={shipDialog.open} onClose={handleShipClose} fullWidth maxWidth="sm">
        <DialogTitle>安排发货</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="SKU"
              size="small"
              fullWidth
              value={shipDialog.sku}
              onChange={(e) => setShipDialog((s) => ({ ...s, sku: e.target.value }))}
            />
            <TextField
              label="数量"
              size="small"
              type="number"
              fullWidth
              value={shipDialog.qty}
              onChange={(e) => setShipDialog((s) => ({ ...s, qty: e.target.value }))}
            />
            <TextField
              label="收件人姓名"
              size="small"
              fullWidth
              value={shipDialog.receiver_name}
              onChange={(e) => setShipDialog((s) => ({ ...s, receiver_name: e.target.value }))}
              placeholder="可空，默认用线索姓名"
            />
            <TextField
              label="收件人手机号"
              size="small"
              fullWidth
              value={shipDialog.receiver_phone}
              onChange={(e) => setShipDialog((s) => ({ ...s, receiver_phone: e.target.value }))}
              placeholder="可空，默认用线索电话"
            />
            <TextField
              label="收件地址"
              size="small"
              fullWidth
              value={shipDialog.receiver_address}
              onChange={(e) => setShipDialog((s) => ({ ...s, receiver_address: e.target.value }))}
              placeholder="可空，默认用线索公司"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleShipClose}>取消</Button>
          <Button variant="contained" color="warning" onClick={handleShipSubmit}>
            确认发货
          </Button>
        </DialogActions>
      </Dialog>

      {/* 物流轨迹 Dialog */}
      <Dialog open={trackingDialog.open} onClose={handleTrackingClose} fullWidth maxWidth="xs">
        <DialogTitle>物流轨迹</DialogTitle>
        <DialogContent>
          {(() => {
            const result = trackingDialog.result;
            if (result == null) {
              return <CircularProgress size={20} />;
            }
            if ("reason" in result) {
              return (
                <Typography variant="body2" color="text.secondary">
                  {result.reason}
                </Typography>
              );
            }
            // 此处 result 已被收窄为成功形态 { provider; status; tracking_no; traces }
            return (
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                  <Chip size="small" label={result.provider} />
                  <Chip size="small" label={result.status} color="error" />
                  <Typography variant="caption" color="text.secondary">
                    {result.tracking_no}
                  </Typography>
                </Stack>
                <Divider sx={{ mb: 1 }} />
                <List dense disablePadding>
                  {result.traces.map((t, i) => (
                    <ListItem key={i} disableGutters>
                      <ListItemText primary={t.desc} secondary={t.time} />
                    </ListItem>
                  ))}
                </List>
              </Box>
            );
          })()}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleTrackingClose}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
