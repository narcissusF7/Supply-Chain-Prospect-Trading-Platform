import type { ReactNode } from "react";
import { Box, Card, CardContent, Typography, useTheme } from "@mui/material";

interface StatCardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  icon?: ReactNode;
  /** 强调色，默认取主题 primary。 */
  color?: string;
}

/** 统计指标卡（仪表盘顶部指标）。 */
export default function StatCard({ title, value, subtitle, icon, color }: StatCardProps) {
  const theme = useTheme();
  const accent = color ?? theme.palette.primary.main;

  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="subtitle2" color="text.secondary">
            {title}
          </Typography>
          {icon && <Box sx={{ color: accent }}>{icon}</Box>}
        </Box>
        <Typography variant="h4" sx={{ mt: 1, fontWeight: 700, color: accent }}>
          {value}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary">
            {subtitle}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
