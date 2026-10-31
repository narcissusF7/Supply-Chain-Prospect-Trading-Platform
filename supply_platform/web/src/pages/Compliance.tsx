import { useCallback, useEffect, useState } from "react";
import {
  Box,
  CircularProgress,
  Grid,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Stack,
  Typography,
} from "@mui/material";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import { api } from "../api";
import { useNotify } from "../notify";
import type { SettingsOut } from "../types";

/**
 * 合规配置：展示当前生效的合规规则（阈值与「系统设置 → 合规配置」联动）。
 * 退订 / 谢绝来电 / PIPL / 呼叫时段 / 频次上限 任一命中即拦截（按优先级短路）。
 */
export default function Compliance() {
  const { notify } = useNotify();
  const [settings, setSettings] = useState<SettingsOut | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSettings(await api.getSettings());
    } catch (err) {
      notify(err instanceof Error ? err.message : "加载配置失败", "error");
    } finally {
      setLoading(false);
    }
  }, [notify]);

  useEffect(() => {
    void load();
  }, [load]);

  const c = settings?.compliance;

  const rules = [
    {
      title: "退订名单 (OPT_OUT)",
      desc: "命中退订名单（手机号 / 统一社会信用代码）即阻断触达。",
    },
    {
      title: "谢绝来电登记 (DO_NOT_CALL)",
      desc: "命中谢绝来电登记即阻断外呼与短信触达。",
    },
    {
      title: `PIPL 同意${c ? (c.require_pilp_consent ? "（强制）" : "（已关闭）") : ""}`,
      desc: c?.require_pilp_consent
        ? "pilp_consent 必须为 True 才允许触达，否则阻断。"
        : "当前已关闭强制要求，未同意用户也可触达（请谨慎评估合规风险）。",
    },
    {
      title: `呼叫时段${c?.enforce_call_window ? ` ${c.call_start_hour}:00–${c.call_end_hour}:00` : "（未强制）"}`,
      desc: c?.enforce_call_window
        ? `外呼（OUTBOUND）强约束在 ${c.call_start_hour}:00–${c.call_end_hour}:00；短信放宽但记录。`
        : "当前未对呼叫时段做强约束，任意时段外呼均可触达。",
    },
    {
      title: `频次上限${c ? ` ${c.frequency_window_days} 日内 ≤ ${c.frequency_cap} 次` : ""}`,
      desc: c
        ? `同一线索 ${c.frequency_window_days} 日内成功触达次数上限为 ${c.frequency_cap} 次，超出即拦截。`
        : "同一线索 7 日内成功触达次数上限为 3 次，超出即拦截。",
    },
  ];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} gutterBottom>
        合规配置
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        触达前横切合规校验（任一命中即拦截，按优先级短路）。阈值与「系统设置 → 合规配置」实时联动；修改后此处自动反映。
      </Typography>

      {loading || settings == null ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Grid container spacing={2}>
          {rules.map((rule, idx) => (
            <Grid item xs={12} md={6} key={rule.title}>
              <Paper variant="outlined" sx={{ p: 2, height: "100%" }}>
                <List disablePadding>
                  <ListItem disableGutters>
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      <VerifiedUserIcon color="primary" />
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography fontWeight={600}>{`${idx + 1}. ${rule.title}`}</Typography>
                        </Stack>
                      }
                      secondary={rule.desc}
                    />
                  </ListItem>
                </List>
              </Paper>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}
