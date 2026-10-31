import { createTheme } from "@mui/material/styles";

/**
 * 管理后台主题：中性蓝灰（slate / blue）为主色调。
 * 字体栈含系统中文字体回退，保证中文显示正常。
 */
const theme = createTheme({
  palette: {
    mode: "light",
    primary: { main: "#475569" }, // slate-600 蓝灰
    secondary: { main: "#2563eb" }, // blue-600
    background: { default: "#f3f4f6", paper: "#ffffff" },
    divider: "#e5e7eb",
  },
  shape: {
    borderRadius: 8,
  },
  typography: {
    fontFamily: [
      "Inter",
      "system-ui",
      "-apple-system",
      "Segoe UI",
      "Roboto",
      "PingFang SC",
      "Hiragino Sans GB",
      "Microsoft YaHei",
      "微软雅黑",
      "sans-serif",
    ].join(","),
    h5: { fontWeight: 700 },
    h6: { fontWeight: 700 },
  },
  components: {
    MuiAppBar: {
      defaultProps: { elevation: 0 },
      styleOverrides: {
        root: { borderBottom: "1px solid #e5e7eb" },
      },
    },
    MuiCard: {
      defaultProps: { elevation: 0 },
    },
    MuiPaper: {
      styleOverrides: {
        outlined: { borderColor: "#e5e7eb" },
      },
    },
  },
});

export default theme;
