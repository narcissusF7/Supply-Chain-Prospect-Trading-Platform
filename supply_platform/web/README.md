# 供应平台 · 管理后台（前端 SPA）

供应平台（FastAPI 后端 MVP）对应的**前端管理后台**，技术栈：

> **Vite + React 18 + TypeScript + MUI 5 + Tailwind CSS**

- **MUI 5**：负责组件（AppBar / Drawer / Table / Chip / Card 等）
- **Tailwind CSS**：负责间距 / 栅格等布局工具类（与 MUI 共存）
- **React Router**：10 个模块路由
- 轻量数据获取：原生 `fetch` 封装（见 `src/api.ts`），无 Redux

---

## 目录结构

```
web/
├── index.html
├── package.json
├── vite.config.ts          # dev proxy: /api → http://localhost:8000
├── tsconfig*.json
├── tailwind.config.js
├── postcss.config.js
├── README.md
└── src/
    ├── main.tsx            # 入口（ThemeProvider + Router + NotifyProvider）
    ├── App.tsx             # 路由表（10 个模块）
    ├── theme.ts            # MUI 主题（中性蓝灰）
    ├── types.ts            # 后端 API 数据契约类型
    ├── api.ts              # fetch 封装（/api/v1 相对路径）
    ├── notify.tsx          # 全局轻提示（Snackbar）
    ├── nav.ts              # 左侧导航配置
    ├── index.css           # Tailwind 指令 + 字体栈
    ├── components/
    │   ├── Layout.tsx          # 左侧导航 + 顶部快捷按钮 + 内容区
    │   ├── DataTable.tsx       # 通用表格（分页）
    │   ├── StatCard.tsx        # 指标卡
    │   ├── StateFunnel.tsx     # 阶段漏斗
    │   ├── SectionPlaceholder.tsx  # “待后端接入”占位
    │   └── ActionPanel.tsx     # 操作按钮 + 结果展示
    └── pages/
        ├── Dashboard.tsx       # 仪表盘
        ├── Leads.tsx           # 线索池
        ├── Ingestion.tsx       # 采集任务
        ├── Scoring.tsx         # 评分模型
        ├── Outreach.tsx        # 触达任务
        ├── Intent.tsx          # 意向工作台
        ├── Contract.tsx        # 签约履约（占位）
        ├── Compliance.tsx      # 合规配置（只读）
        ├── Audit.tsx           # 审计日志
        └── Settings.tsx        # 系统设置（占位）
```

---

## 本地运行

### 1. 先启动后端（必须）

前端通过 Vite dev proxy 将 `/api` 转发到后端 `http://localhost:8000`，因此**后端需先运行**：

```bash
cd supply_platform
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

启动后访问 `http://127.0.0.1:8000/docs` 可见 Swagger，可手动触发 `/seed` / `/collect` / `/score` 等接口灌入数据。

> 前端**不依赖后端 CORS**——dev 下走 Vite 代理，生产下由同源 / 反向代理解决，因此**未给后端加 CORS 中间件**。

### 2. 安装并启动前端

```bash
cd supply_platform/web
npm install
npm run dev
```

打开 `http://localhost:5173` 即可访问管理后台（API 请求经 proxy 打到 `:8000`）。

### 3. 生产构建

```bash
npm install
npm run build      # tsc -b 类型检查 + vite 构建，产物在 dist/
npm run preview    # 本地预览构建产物（含 SPA 路由回退）
```

> 若当前环境**无法联网安装 npm 包**：代码与配置完整、可在标准环境一键 `npm install && npm run build`。请在有网环境执行构建验证；无需因装包失败而停工。

---

## 模块 ↔ 后端接口对应表

| 模块 | 路由 | 调用的后端接口 | 说明 |
| --- | --- | --- | --- |
| 仪表盘 Dashboard | `/` | `GET /leads`、`GET /audit`、`POST /seed`、`POST /collect`、`POST /score`、`POST /outreach?channel=SMS` | 客户端统计总数 / tier / state，含一键流水线 |
| 线索池 Leads | `/leads` | `GET /leads?state=&tier=`、`POST /leads/{id}/intent` | 列表 + 筛选；CONTACTED 可标记意向 |
| 采集任务 Ingestion | `/ingestion` | `POST /seed`、`POST /collect` | 按钮触发，显示 detail |
| 评分模型 Scoring | `/scoring` | `POST /score` | 按钮触发，显示 detail |
| 触达任务 Outreach | `/outreach` | `POST /outreach?channel=SMS` | 按钮触发，显示含合规拦截的 detail |
| 意向工作台 Intent | `/intent` | `GET /leads?state=CONTACTED`、`GET /leads?state=INTERESTED`、`POST /leads/{id}/intent` | CONTACTED 标记意向 + INTERESTED 列表 |
| 签约履约 Contract | `/contract` | —（占位） | 后端 sign/ship 为 stub，待接 e签宝/WMS/快递鸟 |
| 合规配置 Compliance | `/compliance` | —（只读展示） | 五条规则（与 `app/compliance.py` 对齐），阈值在代码/环境变量 |
| 审计日志 Audit | `/audit` | `GET /audit` | 事件类型/线索/智能体/详情/时间 |
| 系统设置 Settings | `/settings` | —（占位） | 角色权限、密钥、服务商对接为后续接入 |

基础路径统一为 `/api/v1`，已在 `src/api.ts` 内封装。

---

## 设计要点

- **API 封装**：`src/api.ts` 统一相对路径 `/api/v1`，GET/POST 封装自动解析 JSON、提取后端 `detail` 作为错误信息。
- **dev 代理避免 CORS**：`vite.config.ts` 将 `/api` → `http://localhost:8000`，前端不显式写宿主地址。
- **类型对齐**：`src/types.ts` 的 `LeadOut` / `AuditOut` 等与 `app/schemas.py` 字段严格对应，未臆造字段。
- **状态机展示**：`NEW → SCORED → CONTACTED → INTERESTED → SIGNED → SHIPPED`（`StateFunnel` 按此顺序展示各状态数量）。
- **中文显示**：主题 `typography.fontFamily` 含 `PingFang SC / Microsoft YaHei / 微软雅黑` 等系统字体回退。

---

## 下一步接入点

- **签约履约 / 系统设置**：后端 sign/ship、角色权限、密钥、服务商对接。
- **采集 / 评分配置 UI**：定时采集任务、多数据源、权重配置（当前为确定性规则）。
- **外呼（AI 外呼）**：当前 outreach 仅 SMS；OUTBOUND 为 mock。
- **真实通道**：阿里云短信（`ALIYUN_SMS_*` 环境变量）、LangGraph 编排开关、LLM 评分扩展点。
