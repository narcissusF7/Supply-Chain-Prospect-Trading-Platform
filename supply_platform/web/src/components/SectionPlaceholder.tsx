import { Box, Paper, Typography } from "@mui/material";
import ConstructionOutlined from "@mui/icons-material/ConstructionOutlined";

interface SectionPlaceholderProps {
  /** 模块标题（可选）。 */
  title?: string;
  /** 模块说明。 */
  description: string;
  /** 后续接入点提示（可选）。 */
  hint?: string;
}

/**
 * 占位组件：用于暂无后端接口的模块，明确标注“待后端接入”。
 */
export default function SectionPlaceholder({ title, description, hint }: SectionPlaceholderProps) {
  return (
    <Paper variant="outlined" sx={{ p: 5, textAlign: "center", bgcolor: "grey.50" }}>
      <Box sx={{ color: "text.disabled", mb: 2 }}>
        <ConstructionOutlined sx={{ fontSize: 56 }} />
      </Box>
      {title && (
        <Typography variant="h6" gutterBottom>
          {title}
        </Typography>
      )}
      <Typography variant="body1" color="text.secondary">
        {description}
      </Typography>
      <Typography variant="body2" color="text.disabled" sx={{ mt: 1.5 }}>
        待后端接入
      </Typography>
      {hint && (
        <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 2 }}>
          {hint}
        </Typography>
      )}
    </Paper>
  );
}
