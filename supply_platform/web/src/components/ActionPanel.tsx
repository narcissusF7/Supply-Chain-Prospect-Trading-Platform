import { useState } from "react";
import { Alert, Box, Button, Paper, Stack, Typography } from "@mui/material";

export interface ActionButton {
  label: string;
  onClick: () => Promise<{ ok: boolean; detail: string }>;
  color?: "primary" | "secondary" | "success" | "warning" | "info";
}

interface ActionPanelProps {
  title?: string;
  buttons: ActionButton[];
  /** 说明区文案（如“后续接入点”）。 */
  note?: string;
  /** 处理中按钮文案。 */
  busyLabel?: string;
}

/**
 * 通用操作面板：一排动作按钮 + 结果展示 + 底部说明。
 * 调用方传入按钮与对应的后端接口调用；结果 detail 以 Alert 展示。
 */
export default function ActionPanel({
  title = "操作",
  buttons,
  note,
  busyLabel = "处理中...",
}: ActionPanelProps) {
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ ok: boolean; detail: string } | null>(null);

  const handle = async (btn: ActionButton) => {
    setBusy(btn.label);
    setResult(null);
    try {
      const res = await btn.onClick();
      setResult(res);
    } catch (err) {
      setResult({ ok: false, detail: err instanceof Error ? err.message : "请求失败" });
    } finally {
      setBusy(null);
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
      <Typography variant="subtitle1" fontWeight={600} gutterBottom>
        {title}
      </Typography>
      <Stack
        direction="row"
        spacing={2}
        flexWrap="wrap"
        useFlexGap
        sx={{ mb: result ? 2 : 0 }}
      >
        {buttons.map((btn) => (
          <Button
            key={btn.label}
            variant="contained"
            color={btn.color ?? "primary"}
            disabled={busy !== null}
            onClick={() => handle(btn)}
          >
            {busy === btn.label ? busyLabel : btn.label}
          </Button>
        ))}
      </Stack>
      {result && (
        <Alert severity={result.ok ? "success" : "error"}>
          {result.detail || (result.ok ? "操作成功" : "操作失败")}
        </Alert>
      )}
      {note && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            {note}
          </Typography>
        </Box>
      )}
    </Paper>
  );
}
