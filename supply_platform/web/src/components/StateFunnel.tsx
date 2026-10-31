import { Box, Chip, Typography } from "@mui/material";
import { LEAD_STATES } from "../types";

interface StateFunnelProps {
  /** 各状态对应的线索数量。 */
  counts: Record<string, number>;
}

/** 各状态颜色（与状态机顺序对应）。 */
const STATE_COLORS: Record<string, string> = {
  NEW: "#94a3b8",
  SCORED: "#60a5fa",
  CONTACTED: "#818cf8",
  INTERESTED: "#34d399",
  SIGNED: "#fbbf24",
  SHIPPED: "#f472b6",
};

/**
 * 阶段漏斗：按状态机顺序用条形展示各状态线索数量（宽度按最大值归一化）。
 */
export default function StateFunnel({ counts }: StateFunnelProps) {
  const max = Math.max(1, ...LEAD_STATES.map((s) => counts[s] ?? 0));

  return (
    <Box>
      {LEAD_STATES.map((state) => {
        const count = counts[state] ?? 0;
        const pct = (count / max) * 100;
        return (
          <Box key={state} sx={{ mb: 1.5 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
              <Chip
                label={state}
                size="small"
                sx={{ bgcolor: STATE_COLORS[state], color: "#fff", fontWeight: 600 }}
              />
              <Typography variant="body2" color="text.secondary">
                {count}
              </Typography>
            </Box>
            <Box sx={{ height: 12, borderRadius: 1, bgcolor: "grey.200", overflow: "hidden" }}>
              <Box
                sx={{
                  width: `${pct}%`,
                  height: "100%",
                  bgcolor: STATE_COLORS[state],
                  transition: "width .3s",
                }}
              />
            </Box>
          </Box>
        );
      })}
    </Box>
  );
}
