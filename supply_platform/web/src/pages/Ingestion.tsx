import { Box, Typography } from "@mui/material";
import ActionPanel from "../components/ActionPanel";
import { api } from "../api";

/**
 * 采集任务：按钮触发 POST /seed 与 POST /collect，显示返回 detail。
 */
export default function Ingestion() {
  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        采集任务
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        写入示例数据（商户 + 合规名单），并从 mock 数据源采集线索、入库去重。
      </Typography>
      <ActionPanel
        title="采集操作"
        buttons={[
          { label: "写入示例数据 (seed)", color: "secondary", onClick: () => api.seed() },
          { label: "采集线索 (collect)", color: "info", onClick: () => api.collect() },
        ]}
        note="说明：定时采集任务与多数据源配置为后续接入；当前采集为 mock 第三方 API（内置种子 / 本地 JSON），按统一主键（统一社会信用代码优先，否则手机号）去重合并。"
      />
    </Box>
  );
}
