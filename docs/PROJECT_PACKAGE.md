# 成熟项目包说明

Version: 1.0
Updated: 2026-07-07

本文是情报官项目交付、部署、验收和后续扩展的总清单。它面向接手项目的工程师、运维人员和情报 Agent 执行人员。

## 1. 包内容

```text
osint-agent-network/
  README.md
  DESIGN.md
  docker-compose.yml
  .env.example
  backend/
  frontend/
  docs/
  data/
  reports/
```

核心交付物：

- 可运行的网页端：`http://127.0.0.1:3008/`
- 可运行的 API：`http://127.0.0.1:8088/api/health`
- SQLite 数据库：`data/osint.sqlite`
- Agent 协议：`docs/AGENT_PROTOCOL.md`
- 编排模型：`docs/ORCHESTRATION_MODEL.md`
- 图谱标准：`docs/GRAPH_TEMPLATE.md`
- UI 设计标准：`DESIGN.md`
- IntelCore 预测标准：PIR、Admiralty Code、ACH、I&W、BLUF 和定向采集计划。
- 空白 Alibaba/CRM Lead 逆向补全 SOP：锚点提取、拉美复姓消歧、公开来源补全、硬资产卡位、红队剧本。

## 2. 环境要求

本地开发：

- Python 3.11+
- Node.js 22+
- npm
- SQLite

<production-host> 部署：

- Docker Compose，或 Python/Node 原生服务管理。
- OSINT 工具按实际需要安装在固定路径。
- 推荐先用 `scripts/start.sh` 做原生烟测；长期运行使用用户级 systemd。
- 详细部署、烟测、备份和回滚步骤见 `docs/N100_DEPLOYMENT_RUNBOOK.md`。
- 最新 <production-host> 实际任务测试、ProjectDiscovery 域名 quick 链路达标、质量闸门修复、阻断状态修复和复测结论见 `docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md`。
- 当前阶段收尾、验证证据和剩余可选工作见 `docs/STAGE_CLOSURE_2026-07-07.md`。
- 2026-07-06 队列/runtime 阶段的历史临时收尾见 `docs/TEMPORARY_CLOSURE_2026-07-06.md`。
- 真实工具按需启用，不要求常驻后台；接线、剩余缺口和验收命令见 `docs/REAL_TOOL_ENABLEMENT.md`。

## 3. 启动方式

### 原生启动

后端：

```bash
cd /path/to/osint-agent-network
PYTHONPATH=backend python3 -m app.main
```

前端：

```bash
cd /path/to/osint-agent-network/frontend
npm install
npm run dev
```

服务器运行时推荐使用：

```bash
cd /opt/osint-agent-network
bash scripts/start.sh
bash scripts/status.sh
bash scripts/stop.sh
```

<production-host> 长期运行推荐使用用户级 systemd：

```bash
systemctl --user status osint-agent-network-api.service osint-agent-network-web.service
systemctl --user restart osint-agent-network-api.service osint-agent-network-web.service
```

### Compose 启动

```bash
cd /path/to/osint-agent-network
cp .env.example .env
docker compose up
```

## 4. 配置清单

生产环境建议至少设置：

```bash
APP_HOST=0.0.0.0
APP_PORT=8088
WEB_PORT=3008
OSINT_DB_PATH=/opt/osint-agent-network/data/osint.sqlite
AGENT_API_TOKEN=<strong-agent-token>
ADMIN_API_TOKEN=<strong-admin-token>
OSINT_LLM_BASE_URL=http://192.0.2.10:6780/v1
OSINT_LLM_API_KEY=<redacted>
OSINT_LLM_MODEL=gpt-5.4
```

前端生产构建需要写入 API 地址和管理 Token：

```bash
cd /opt/osint-agent-network/frontend
cat > .env.production <<'EOF'
VITE_API_BASE_URL=http://192.0.2.10:8088
VITE_ADMIN_API_TOKEN=<same-value-as-ADMIN_API_TOKEN>
EOF
```

工具路径按实际安装补齐：

```bash
SHERLOCK_COMMAND=python3
THEHARVESTER_COMMAND=python3
AMASS_COMMAND=amass
SUBFINDER_COMMAND=<osint-bin>/subfinder
HTTPX_COMMAND=<osint-bin>/httpx
KATANA_COMMAND=<osint-bin>/katana
OFFICIAL_SITE_SEARCH_BASE_URL=
SPIDERFOOT_BASE_URL=
PHONEINFOGA_BASE_URL=
GHUNT_COMMAND=ghunt
RECONNG_COMMAND=recon-ng
```

## 5. 数据目录

| 路径 | 用途 | 是否建议备份 |
| --- | --- | --- |
| `data/osint.sqlite` | 主数据库 | 是 |
| `data/jobs/` | 工具任务产物 | 是 |
| `data/artifacts/` | 大型原始产物 | 按需 |
| `data/screenshots/` | UI 验证截图 | 按需 |
| `data/snapshots/` | 演示/迁移快照 | 是 |
| `reports/` | 报告导出 | 是 |

不要把 `.env`、Cookie、API Key 或私密工具配置提交到项目包中。

## 6. 标准验证

每次交付前运行：

```bash
cd /path/to/osint-agent-network
bash scripts/verify.sh
```

或者拆分运行：

```bash
cd /path/to/osint-agent-network
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_agent_protocol backend.tests.test_worker backend.tests.test_graph
```

```bash
cd /path/to/osint-agent-network/frontend
npm run check:ui-copy
node --experimental-strip-types ./scripts/test-ui-state.ts
node --experimental-strip-types ./scripts/test-graph-helpers.ts
node --experimental-strip-types ./scripts/test-investigation-bundle.ts
npm run build
```

人工验证：

- 后端 `GET /api/health` 返回 `{"status":"ok"}`。
- 前端 3008 能打开。
- 任务列表能看到历史任务。
- 企业任务详情能看到职责型 Agent 队列。
- 图谱固定槽位完整，空位显示 `待补充`。
- 细彩线连接证据、来源和结论。

## 7. Agent 执行规范

外部 Agent 接入时：

1. 注册 Agent。
2. 认领任务。
3. 写入事件。
4. 写入实体。
5. 写入证据。
6. 写入关系。
7. 生成报告并完成任务。

不得只写报告不写结构化数据。网页端图谱依赖结构化数据生成。

企业和决策人任务还必须遵守 IntelCore 情报循环：

- 先定义 3-5 条 PIR。
- 如果是 Alibaba/CRM 空白 Lead，先提取姓名、姓名变体、国家、买家等级、注册/建档/咨询时间、采购品类、年采购额等锚点。
- 抓取后做分类清洗和去重。
- 对关键事实标注 Admiralty Code。
- 用交叉确认决定哪些信息进入主图谱。
- 对未闭合事实生成 directed collection 下一步采集计划。
- 最终报告用 ACH 证伪竞争性假设，用 I&W 征候矩阵预测下一步动作，用 BLUF 第一段交付核心判断。
- 候选公司事实和候选身份匹配必须分开打分；不能因为某家公司真实存在，就默认它属于截图里的买家。
- 业务建议可以要求透明补证，例如公司名、网站、WhatsApp、图纸、数量、目的港、标准和交付期。
- 系统只输出行动建议，不自动执行欺骗、干扰、投放或反情报动作。

## 8. 项目当前状态

已完成：

- 本地 API 与前端联通。
- SQLite 持久化。
- 多工具适配器框架。
- ProjectDiscovery 社区工具链：`subfinder`、`httpx`、`katana`，以及内置 `official_site_extractor` 官网解析器。
- 可选官网搜索层：`official_site_search` 支持 SearXNG 兼容端点，为 `company` 和 `sparse_lead` 任务补官网候选 URL。
- `company`、`sparse_lead`、`domain`、`email`、`username`、`phone`、`url` 等目标类型与职责型 Agent 队列。
- 依赖感知队列、SQLite 可恢复后台 worker 队列、并发保护、递进式推演和 IntelCore 预测分析输出合同。
- Intelligence Core v3：任务需求层、事实晋级、交叉验证矩阵和专业白皮书结构。
- 情报循环式工作流：初采、首轮验证、有限定向扩展、深度工具门禁、最终分析。
- 缺口到工具自动补采计划：`gap_analysis`、`gap_tool_plan` 和
  `gap_followup_summary` 会解释卡点、缺失证据、可用工具、阻断工具和人工复核动作。
- 完成策略：区分 strict、limited、continue_collection、
  ready_for_human_decision、blocked_by_environment 和 failed，避免工具耗尽后无意义循环。
- 官网 URL/domain 交叉验证归一化：等价官网写法不会产生误冲突，真实冲突会在矩阵理由中列出候选域名和来源族。
- 管理写接口 Token 保护，Agent 写回接口 Token 保护。
- 空白 Alibaba/CRM Lead 逆向补全 SOP。
- 企业与决策人并列图谱模板。
- 证据、实体、关系图谱生成。
- 风险复核、白皮书报告和质量闸门。
- 完整验证脚本：后端测试、前端状态检查、图谱/报告 bundle 检查、Vite build。
- Markdown、HTML 和 PDF 报告导出，导出内容复用结构化报告并应用脱敏。
- 稳定性收尾包：schema 版本记录、`/api/system/status`、`scripts/backup.sh`、`scripts/healthcheck.sh` 和前端系统自检面板。
- 运维增强包：`/api/tools/health` 真实工具就绪检查、固定样本回归库、`BACKUP_KEEP_LAST` 备份保留策略、user-level systemd 定时备份和 `scripts/production_readiness.py` 成熟版本验收脚本。
- <production-host> 域名 quick 链路已达到当前设计目标：最终任务 `<final-domain-task-id>` 为 `COMPLETED`，质量分 `78.1 / 100`，`subfinder`、`httpx`、`katana`、`official_site_extractor` 全部完成，失败和阻断均为 `0`。

已验证基线：

- `bash scripts/verify.sh` 通过。
- backend unittest：`411 tests OK`。
- 回归 smoke：`4` cases / `0` failed。
- frontend helper checks、Vitest `9` tests 和 Vite production build 通过。

需要后续增强：

- 用户权限分层和审计日志。
- 证据来源等级、人工复核状态、复核备注和复核时间字段。
- 更丰富的公开安全实际任务样本、完成率统计、误冲突率统计和补采命中率统计。
- 打包式报告下载、导出审计记录和证据附件整理。
- 多主机 worker 需要时再评估外部队列 broker。

## 9. 交付验收标准

项目包可被认为成熟可交付，需要满足：

- 一条命令能启动后端，一条命令能启动前端。
- README 能让新人 15 分钟内跑起来。
- Agent 协议能让外部执行器完成写回。
- 图谱模板不会因数据增多而失控。
- 每条主结论都有来源链。
- 测试命令通过。
- `.env.example` 完整，真实 `.env` 不进入包。

## 10. 故障排查

3008 打不开：

- 检查前端是否运行。
- 检查端口是否被占用。
- 检查 Vite 控制台报错。

页面无数据：

- 检查后端是否运行。
- 检查 `VITE_API_BASE_URL` 或 Vite 代理配置。
- 检查 `data/osint.sqlite` 是否存在。

Agent 写回 401：

- 检查 `AGENT_API_TOKEN`。
- 请求头必须是 `Authorization: Bearer <token>`。

前端管理操作 401：

- 检查后端 `.env` 中的 `ADMIN_API_TOKEN`。
- 检查 `frontend/.env.production` 中的 `VITE_ADMIN_API_TOKEN`。
- 修改前端环境变量后必须重新 `npm run build`。

后端健康检查失败：

- 使用 `curl -sS http://127.0.0.1:8088/api/health`。
- 当前后端不处理 `HEAD`，`curl -I` 返回异常不能代表服务不可用。

系统自检：

- 使用 `curl -sS http://127.0.0.1:8088/api/system/status` 查看数据库、schema、任务、队列、工具和脚本状态。
- 使用 `bash scripts/healthcheck.sh` 做部署后健康检查。
- 使用 `bash scripts/backup.sh` 做手动备份。

图谱为空：

- 检查任务详情是否有 `entities`、`evidence`、`relationships`。
- 检查前端是否调用了 `graphDisplayNodes`。
- 空槽位应显示 `待补充`，如果整图为空说明前端渲染或 API 详情异常。
