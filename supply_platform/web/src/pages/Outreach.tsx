import { Box, Typography } from "@mui/material";
import ActionPanel from "../components/ActionPanel";
import { api } from "../api";

/**
 * 触达任务：按钮触发 POST /outreach?channel=SMS（对所有 SCORED 线索触达，内部必过合规）。
 */
export default function Outreach() {
  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        触达任务
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        对所有 SCORED 线索批量触达（短信），发送前必过合规中间件。
      </Typography>
      <ActionPanel
        title="触达操作"
        buttons={[{ label: "短信触达 (SMS)", color: "warning", onClick: () => api.outreach("SMS") }]}
        note="说明：外呼（AI 外呼）为 mock，后续接入真实运营商 / AI 外呼 SDK；合规拦截情况会在返回 detail 中逐条体现（退订 / 谢绝来电 / 时段 / 频次 / PIPL 同意）。"
      />
    </Box>
  );
}
