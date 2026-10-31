import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { Alert, Snackbar } from "@mui/material";

export type NotifySeverity = "success" | "info" | "warning" | "error";

interface NotifyContextValue {
  /** 弹出一条轻提示。 */
  notify: (message: string, severity?: NotifySeverity) => void;
}

const NotifyContext = createContext<NotifyContextValue>({
  notify: () => undefined,
});

/** 在任意组件中获取 notify 方法。 */
export function useNotify(): NotifyContextValue {
  return useContext(NotifyContext);
}

interface SnackState {
  open: boolean;
  message: string;
  severity: NotifySeverity;
}

/**
 * 全局轻提示 Provider：包裹应用后，任意页面 / 布局均可调用 notify。
 * 用于展示后端接口返回的 detail 或网络错误。
 */
export function NotifyProvider({ children }: { children: ReactNode }) {
  const [snack, setSnack] = useState<SnackState>({
    open: false,
    message: "",
    severity: "success",
  });

  const value = useMemo<NotifyContextValue>(
    () => ({
      notify: (message: string, severity: NotifySeverity = "success") =>
        setSnack({ open: true, message, severity }),
    }),
    [],
  );

  const handleClose = (_event?: unknown, reason?: string) => {
    if (reason === "clickaway") return;
    setSnack((prev) => ({ ...prev, open: false }));
  };

  return (
    <NotifyContext.Provider value={value}>
      {children}
      <Snackbar
        open={snack.open}
        autoHideDuration={4000}
        onClose={handleClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert onClose={handleClose} severity={snack.severity} variant="filled">
          {snack.message}
        </Alert>
      </Snackbar>
    </NotifyContext.Provider>
  );
}
