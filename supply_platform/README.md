# 供应平台 supply_platform（MVP 骨架）

多智能体平台前半闭环最小可用骨架：**采集 → 评分 → 入库去重 → 合规 →（模拟）触达**。

- 采集：mock 第三方 API（内置种子/本地 JSON），预留真实 API 适配接口
- 评分：确定性规则打分，分层 A/B/C，预留 LLM 评分扩展点
- 入库：按统一主键（统一社会信用代码优先，否则手机号）去重合并
- 合规：触达前横切校验（退订 / 谢绝来电 / 时段 / 频次 / PIPL 同意）
- 触达：模拟短信通道（只打印+记日志），发送前必过合规中间件
- 状态机：NEW→SCORED→CONTACTED→INTERESTED→SIGNED→SHIPPED，带 guard + 幂等
- 审计：所有触达 / 合规 / 状态变更留痕
- 三个智能体：data_agent / marketing_agent / fulfillment_agent（独立模块 + 清晰函数边界）

## 技术栈

Python 3.11 · FastAPI · SQLAlchemy 2.0 · SQLite（文件库，零外部依赖）· Pydantic v2 · uvicorn · pytest

## 运行步骤

```bash
cd supply_platform
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 启动（uvicorn，启动时自动建表）
uvicorn app.main:app --reload --port 8000
```

服务启动后访问 `http://127.0.0.1:8000/docs` 可见 Swagger。

### 调用示例（curl）

```bash
# 健康检查
curl http://127.0.0.1:8000/api/v1/health

# 写入示例数据（商户 + 合规名单）
curl -X POST http://127.0.0.1:8000/api/v1/seed

# 从 mock 采集并入库
curl -X POST http://127.0.0.1:8000/api/v1/collect

# 对 NEW 线索评分分层 → SCORED
curl -X POST http://127.0.0.1:8000/api/v1/score

# 列表/筛选
curl "http://127.0.0.1:8000/api/v1/leads?state=SCORED&tier=A"

# 对 SCORED 线索触达（内部过合规中间件）
curl -X POST "http://127.0.0.1:8000/api/v1/outreach?channel=SMS"

# 标记意向 CONTACTED → INTERESTED（演示）
curl -X POST http://127.0.0.1:8000/api/v1/leads/1/intent

# 审计日志
curl http://127.0.0.1:8000/api/v1/audit
```

### 跑测试

```bash
pip install -r requirements.txt
pytest -q
```

测试使用独立临时 SQLite 库，覆盖：状态机非法迁移 / guard / 幂等、合规五项拦截、去重合并、频次上限、触达幂等。

## 设计要点

- **独立会话/隔离**：各 agent 以独立模块 + 清晰函数边界实现，即便 MVP 为进程内函数，也通过模块边界表达“隔离”。合规守护为横切中间件，触达前强制调用。
- **状态机单一事实源**：`lead_states` 表即状态唯一来源，`transition()` 校验非法迁移、guard（仅当前状态归属 agent 可迁移）、幂等（同目标状态只生效一次）、事务内提交。
- **去重与频次**：去重用 `unified_key` 唯一约束；频次用 `contact_tasks` 窗口计数；触达幂等用 `contact_tasks.dedup_key` 唯一约束。

## 扩展点（未来接真实能力）

- **第三方 API 适配**：替换 `data_agent.fetch_from_api()` 为真实请求，返回结构同构即可。
- **LLM 评分**：`data_agent.score()` 中已标注扩展点，替换为 LLM 推理。
- **真实短信/外呼**：`mock_channels.mock_sms_send / mock_outbound` 替换为阿里云 SMS / 运营商 SDK。
- **电子签约 / WMS / 物流**：`mock_channels.mock_e_sign / mock_wms / mock_logistics` 占位待接 e签宝 / 仓储 / 快递。
- **编排**：`orchestrator.dispatch()` 当前为确定性 switch，未来替换为 LangGraph / LM 编排，按状态图自动路由节点。
- **合规时钟/时区**：`ComplianceGuard._now()` 预留接真实时钟与多时区。

> 若环境无法联网装包：代码仍可直接 `import`、逻辑自洽；请在有网环境 `pip install` 后运行 uvicorn 与 pytest。

---

## 改造一：LangGraph 状态图编排

`app/graph.py` 用 `langgraph.graph.StateGraph` + `MemorySaver`(checkpointer) 构建状态机，将原本确定性的 `orchestrator.dispatch` 升级为**按状态条件路由**的图编排。

设计意图（落地"3 独立 agent 会话 + 按状态派活"）：
- **每条线索独立会话/状态**：每个 lead 以 `thread_id = str(lead_id)` 调用 `graph.invoke`，由 MemorySaver 隔离不同线索的图状态。
- **节点 = agent 动作**：`collect_node / score_node / outreach_node / intent_node / sign_node / ship_node`，分别调用 `data_agent / marketing_agent / fulfillment_agent`，并调用 `state_machine.transition` 推进状态（guard / 幂等 / 事务由 state_machine 保证）。
- **conditional edges 按状态路由**：`entry_router` 及 `_route_*` 从 DB 实时读取线索当前状态决定下一节点；非法迁移会被 `transition` 的 guard 拒绝，节点据此安全停在 `END`。

`orchestrator.dispatch(lead_id)` 公开签名保持不变（main.py 与测试依赖）。内部优先级：LangGraph 编排 →（未安装或异常）确定性回退实现。代码顶部以 `try/except` 容错 import，`langgraph` 缺失时 `LANGGRAPH_AVAILABLE=False`，逻辑自洽、可运行。

## 改造二：真实阿里云短信通道

`app/channels/aliyun_sms.py` 实现真实短信通道，含**多级回退**：

1. 优先使用官方 SDK `alibabacloud_dysmsapi20170525`；
2. SDK 不可用时回退 **RPC 签名 V1 原始 HTTP**（HMAC-SHA1，Action=SendSms，Version=2017-05-25，RegionId=cn-hangzhou，参数 SignName/TemplateCode/PhoneNumbers/TemplateParam，严格按阿里云 RPC 签名规范拼接，用标准库 `urllib` 无需第三方依赖）；
3. 环境变量（凭据）缺失 → 回退 **mock**（打印 + 记日志），保证无凭据也能本地跑通；
4. **发送前强制过合规中间件** `ComplianceGuard.check`（退订 / 谢绝来电 / 时段 / 频次 / PIPL），合规不通过 **绝不调用短信接口**。

`marketing_agent.outreach` 的 SMS 分支已改为调用 `aliyun_sms.send_sms`（带回退）；**外呼（OUTBOUND）仍保留 mock**，本次不做真实外呼。

### 阿里云短信环境变量

```bash
export ALIYUN_SMS_ACCESS_KEY_ID=your_access_key_id
export ALIYUN_SMS_ACCESS_KEY_SECRET=your_access_key_secret
export ALIYUN_SMS_SIGN_NAME=你的签名
export ALIYUN_SMS_TEMPLATE_CODE=SMS_123456789
```

- 缺失任意一个 → 自动回退 mock（本地无凭据也可运行）。
- 真实模板需包含 `content` 变量（见 `_build_template_param`），或按需调整映射。
- 官方 SDK 为可选：`pip install alibabacloud_dysmsapi20170525`；不装则走 RPC 实现。

### 运行示例（含编排 + 真实通道）

```bash
cd supply_platform
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 可选：pip install alibabacloud_dysmsapi20170525
# 可选：export ALIYUN_SMS_ACCESS_KEY_ID=... 等四个变量启用真实短信

uvicorn app.main:app --reload --port 8000

# 写入示例数据并跑通前半闭环（outreach 走真实/回退短信通道）
curl -X POST http://127.0.0.1:8000/api/v1/seed
curl -X POST http://127.0.0.1:8000/api/v1/collect
curl -X POST http://127.0.0.1:8000/api/v1/score
curl -X POST "http://127.0.0.1:8000/api/v1/outreach?channel=SMS"

# 按状态派活（langgraph 启用时由状态图驱动；否则确定性回退）
curl -X POST http://127.0.0.1:8000/api/v1/dispatch/1
```

### 跑测试

```bash
pytest -q
```

测试使用独立临时 SQLite 库，覆盖：状态机非法迁移 / guard / 幂等、合规五项拦截、去重合并、频次上限、触达幂等（既有 12 例），以及本改造新增：
- 无阿里云凭据时回退 mock 仍触达成功、且不调用真实发送；
- 配置凭据时通道选择正确（monkeypatch 注入 fake client，避免真实发信）；
- 合规不通过时绝不调用短信接口；
- `orchestrator.dispatch` 在未启用 langgraph 时回退确定性实现仍可跑通。

> 若环境无法联网装 `langgraph`/`langchain-core`：编排自动回退确定性实现，`pytest` 全绿；代码 import 正常、逻辑自洽。安装后再运行即启用 LangGraph 编排。

## 下一步扩展点

- **LangGraph 中断/人工确认**：在 `CONTACTED` 处用 `interrupt()` 暂停等待意向反馈，替代当前的 `mark_intent` 端点。
- **真实外呼**：将 `marketing_agent.outreach` 的 OUTBOUND 分支接入运营商/AI 外呼 SDK。
- **真实履约**：`fulfillment_agent.sign/ship` 接入 e签宝/法大大、WMS、快递 100/顺丰（占位见 `mock_channels`）。
- **观测与重试**：为节点加 `try/except` + 重试策略，或将失败事件写入 `AuditLog`。
- **第三方数据/LLM 评分**：`data_agent.fetch_from_api` 与 `score()` 的扩展点。
