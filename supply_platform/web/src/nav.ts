import type { ComponentType } from "react";
import DashboardIcon from "@mui/icons-material/Dashboard";
import PeopleIcon from "@mui/icons-material/People";
import CloudDownloadIcon from "@mui/icons-material/CloudDownload";
import ScoreIcon from "@mui/icons-material/Score";
import CampaignIcon from "@mui/icons-material/Campaign";
import ThumbUpIcon from "@mui/icons-material/ThumbUp";
import HandshakeIcon from "@mui/icons-material/Handshake";
import VerifiedUserIcon from "@mui/icons-material/VerifiedUser";
import HistoryIcon from "@mui/icons-material/History";
import SettingsIcon from "@mui/icons-material/Settings";

/** 左侧导航的单个模块项。 */
export interface NavItem {
  key: string;
  label: string;
  path: string;
  icon: ComponentType;
}

/** 10 个模块导航（顺序即管理后台调性）。 */
export const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", label: "仪表盘", path: "/", icon: DashboardIcon },
  { key: "leads", label: "线索池", path: "/leads", icon: PeopleIcon },
  { key: "ingestion", label: "采集任务", path: "/ingestion", icon: CloudDownloadIcon },
  { key: "scoring", label: "评分模型", path: "/scoring", icon: ScoreIcon },
  { key: "outreach", label: "触达任务", path: "/outreach", icon: CampaignIcon },
  { key: "intent", label: "意向工作台", path: "/intent", icon: ThumbUpIcon },
  { key: "contract", label: "签约履约", path: "/contract", icon: HandshakeIcon },
  { key: "compliance", label: "合规配置", path: "/compliance", icon: VerifiedUserIcon },
  { key: "audit", label: "审计日志", path: "/audit", icon: HistoryIcon },
  { key: "settings", label: "系统设置", path: "/settings", icon: SettingsIcon },
];
