import { useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  AppBar,
  Box,
  Button,
  CircularProgress,
  Divider,
  Drawer,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Toolbar as MuiToolbar,
  Typography,
} from "@mui/material";
import { NAV_ITEMS } from "../nav";
import { api } from "../api";
import { useNotify } from "../notify";

const DRAWER_WIDTH = 240;

/**
 * 应用整体布局：
 * - 左侧固定 MUI Drawer 导航（10 个模块）
 * - 顶部 AppBar 显示标题与“健康 / 种子 / 采集 / 评分”快捷按钮
 * - 右侧内容区渲染当前路由页面（Outlet）
 */
export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { notify } = useNotify();
  const [busy, setBusy] = useState<string | null>(null);

  const runAction = async (
    key: string,
    fn: () => Promise<{ ok: boolean; detail: string }>,
  ) => {
    setBusy(key);
    try {
      const res = await fn();
      notify(res.detail || (res.ok ? "操作成功" : "操作失败"), res.ok ? "success" : "error");
    } catch (err) {
      notify(err instanceof Error ? err.message : "请求失败", "error");
    } finally {
      setBusy(null);
    }
  };

  const handleHealth = async () => {
    setBusy("health");
    try {
      const res = await api.health();
      notify(`服务状态：${res.status}`, "success");
    } catch (err) {
      notify(err instanceof Error ? err.message : "健康检查失败", "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Box sx={{ display: "flex", minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar
        position="fixed"
        color="primary"
        sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}
      >
        <Toolbar>
          <Typography variant="h6" noWrap component="div" sx={{ flexGrow: 1 }}>
            供应平台 · 管理后台
          </Typography>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
            <Button color="inherit" size="small" disabled={busy === "health"} onClick={handleHealth}>
              {busy === "health" ? <CircularProgress size={16} color="inherit" /> : "健康"}
            </Button>
            <Button color="inherit" size="small" disabled={busy === "seed"} onClick={() => runAction("seed", api.seed)}>
              种子
            </Button>
            <Button color="inherit" size="small" disabled={busy === "collect"} onClick={() => runAction("collect", api.collect)}>
              采集
            </Button>
            <Button color="inherit" size="small" disabled={busy === "score"} onClick={() => runAction("score", api.score)}>
              评分
            </Button>
          </Box>
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
      >
        <MuiToolbar />
        <Divider />
        <Box sx={{ overflow: "auto", p: 1 }}>
          <List disablePadding>
            {NAV_ITEMS.map((item) => {
              const selected =
                item.path === "/"
                  ? location.pathname === "/"
                  : location.pathname.startsWith(item.path);
              const Icon = item.icon;
              return (
                <ListItemButton
                  key={item.key}
                  selected={selected}
                  onClick={() => navigate(item.path)}
                >
                  <ListItemIcon sx={{ minWidth: 40 }}>
                    <Icon />
                  </ListItemIcon>
                  <ListItemText primary={item.label} />
                </ListItemButton>
              );
            })}
          </List>
        </Box>
      </Drawer>

      <Box
        component="main"
        className="p-6"
        sx={{ flexGrow: 1, width: { sm: `calc(100% - ${DRAWER_WIDTH}px)` } }}
      >
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
}
