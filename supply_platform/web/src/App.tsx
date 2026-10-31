import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Leads from "./pages/Leads";
import Ingestion from "./pages/Ingestion";
import Scoring from "./pages/Scoring";
import Outreach from "./pages/Outreach";
import Intent from "./pages/Intent";
import Contract from "./pages/Contract";
import Compliance from "./pages/Compliance";
import Audit from "./pages/Audit";
import Settings from "./pages/Settings";

/**
 * 路由表：所有页面均在 Layout（左侧导航 + 顶部栏）内渲染。
 * 10 个模块对应 10 条路由。
 */
export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/ingestion" element={<Ingestion />} />
        <Route path="/scoring" element={<Scoring />} />
        <Route path="/outreach" element={<Outreach />} />
        <Route path="/intent" element={<Intent />} />
        <Route path="/contract" element={<Contract />} />
        <Route path="/compliance" element={<Compliance />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}
