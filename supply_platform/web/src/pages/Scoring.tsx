import { Box, Typography } from "@mui/material";
import ActionPanel from "../components/ActionPanel";
import { api } from "../api";

/**
 * 评分模型：按钮触发 POST /score（对所有 NEW 线索评分分层）。
 */
export default function Scoring() {
  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        评分模型
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        对所有 NEW 线索做确定性规则打分并分层 A / B / C。
      </Typography>
      <ActionPanel
        title="评分操作"
        buttons={[{ label: "评分分层 (score)", color: "primary", onClick: () => api.score() }]}
        note="说明：当前评分模型为确定性规则，分层 A/B/C；权重配置 UI 为后续接入，预留 LLM 评分扩展点。"
      />
    </Box>
  );
}
