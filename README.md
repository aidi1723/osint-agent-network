# OSINT Agent Network / 情报官

面向授权公开信息调研的多 Agent 情报工作台。系统把企业、决策人、联系方式、社媒足迹、证据来源、上下游关系和采购意图整理到同一个任务闭环中，最终在网页端生成固定图谱和报告。

> 使用边界：本项目只用于授权范围内的公开来源信息整理、证据留痕和人工复核。不包含攻击、绕过、账号接管、凭证获取、隐蔽规避或非公开数据访问能力。

> 预测边界：IntelCore 预测层只输出判断、概率、风险场景和行动建议，不自动执行欺骗、干扰、投放或反情报动作。

> 许可边界：本项目以 GNU GPL v3 发布，SPDX 标识为 `GPL-3.0-only`。分发、修改和再分发必须遵守 [LICENSE](LICENSE)；第三方依赖仍按各自许可证执行。

## 当前能力

- 多目标类型：`company`、`sparse_lead`、`domain`、`subdomain`、`email`、`username`、`phone`、`ip`、`url`、`profile_url`。
- 多 Agent 编排：企业情报、社媒情报、联系方式发现、上下游映射、采购意图、交叉验证、分析评价。
- 工具适配器：Sherlock、Maigret、Socialscan、theHarvester、Amass、Subfinder、httpx、Katana、SpiderFoot、Recon-ng、GHunt、PhoneInfoga、Profile Parser、Company News、Official Site Extractor、**海关供应链分析**。
- **海关供应链挖掘**：基于跨境魔方API，一键查询企业的上下游贸易伙伴，自动识别客户和供应商关系，零额外成本。详见 [docs/CUSTOMS_SUPPLY_CHAIN.md](docs/CUSTOMS_SUPPLY_CHAIN.md)
- **智能情报聚合**：自动从多个工具输出中聚合联系方式（邮箱/电话）、社交媒体账号、产品信息，一站式展示。详见 [docs/INTELLIGENCE_AGGREGATION.md](docs/INTELLIGENCE_AGGREGATION.md)
- 情报工具中枢：按目标类型、策略和运行配置规划工具路线，缺服务或凭证时自动跳过并给出原因。
- 递进式推演：从官网、邮箱、电话、新闻、社媒主页等高价值线索继续规划下一步工具任务，并保留 `inferred_from` 来源链。
- IntelCore 预测层：用 PIR、Admiralty Code、ACH、I&W 征候矩阵和 BLUF，把成熟情报转成前瞻判断和行动建议。
- Intelligence Core v3：PIR/EEI 情报需求、事实晋级、交叉验证矩阵、ACH/I&W 白皮书结构。
- 空白 Lead 逆向补全：针对 Alibaba/CRM 中只有姓名、国家、等级、时间的弱线索，按锚点提取、复姓消歧、公开企业/社媒/海关候选、硬资产卡位和红队剧本补全。
- 弱线索买家任务使用 `sparse_lead` 类型，先把截图或 CRM 可见字段写成平台锚点，再做候选主体发现、身份匹配评分、ACH 场景判断和 BLUF 报告。系统不会绕过平台隐私设置，也不会把公开公司负责人自动等同为账号操作者。
- 证据闭环：实体、证据、关系、来源工具、置信度、报告摘要统一写回 API。
- 图谱模板：固定 23 个位置，企业信息和决策人画像并列展示，证据以细彩线连接到结论。
- 前端看板：任务创建、任务列表、Agent 队列、图谱、风险复核、报告展示、**供应链分析面板**、**情报汇总面板**。
- 本地持久化：默认 SQLite，数据文件在 `data/osint.sqlite`。

## 架构

```text
frontend/        React + TypeScript + Vite 管理界面，默认端口 3008
backend/         Python http.server API、SQLite Store、Worker、Agent CLI、工具适配器
docs/            协议、编排模型、图谱模板、项目包交付说明
data/            SQLite 数据库、截图、快照、任务产物
reports/         报告输出目录
docker-compose.yml
```

运行时分为四层：

- Web UI：展示任务、Agent 队列、图谱、证据链和报告。
- API Hub：提供 `/api/*` 接口，保存任务、实体、证据、关系和报告。
- Intel Tool Gateway：提供 `/api/tools/plan` 和 `agent_client plan-tools`，统一决定哪些底层工具应该被调用。
- Worker：执行本地 `tool_agent` 工具任务，并按情报循环阶段运行已内置的职责型 Agent；未内置能力仍可由外部 Agent 认领处理。
- External Agents：Codex Desktop、<production-host> 上的 OpenHuman/CLI Agent 或其他可调用 HTTP 的执行器。

## 快速启动

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

服务器上可以使用项目脚本按需管理：

```bash
cd /opt/osint-agent-network
bash scripts/start.sh
bash scripts/status.sh
bash scripts/stop.sh
```

N100 长期运行推荐使用用户级 systemd：

```bash
ssh <production-host>
systemctl --user status osint-agent-network-api.service osint-agent-network-web.service
systemctl --user restart osint-agent-network-api.service osint-agent-network-web.service
```

N100 当前实测项目目录为 `<production-path>`；`/opt/osint-agent-network` 是文档中的通用部署模板路径。Web 构建使用 `frontend/.env.production` 固定 `VITE_API_BASE_URL=http://192.0.2.10:8088`，避免浏览器从 3008 端口误请求 API。

访问：

- Web UI: `http://127.0.0.1:3008/`
- API health: `http://127.0.0.1:8088/api/health`
- System status: `http://127.0.0.1:8088/api/system/status`
- Tool health: `http://127.0.0.1:8088/api/tools/health`

<production-host> 局域网部署后的访问地址：

- Web UI: `http://192.0.2.10:3008/`
- API health: `http://192.0.2.10:8088/api/health`
- System status: `http://192.0.2.10:8088/api/system/status`
- Tool health: `http://192.0.2.10:8088/api/tools/health`

如果 3008 打不开，先确认两个进程都在运行，并用 `curl -sS http://127.0.0.1:8088/api/health` 检查后端。后端不支持 `HEAD`，不要用 `curl -I` 判断健康状态。

## Docker Compose

开发模式：

```bash
cd /path/to/osint-agent-network
cp .env.example .env
docker compose up
```

Compose 会启动：

- `api`: `0.0.0.0:8088`
- `web`: `0.0.0.0:3008`

生产镜像模式：

```bash
cd /path/to/osint-agent-network
cp .env.example .env
# 设置 APP_ENV=production，并配置 ADMIN_API_TOKEN、AGENT_API_TOKEN、READ_API_TOKEN
docker compose -f docker-compose.prod.yml up --build
```

<production-host> 部署时建议把项目放在 `/opt/osint-agent-network`，并把 `.env` 中的工具路径、模型中转地址和 API Token 配好。

如果只是临时试运行，可使用 `bash scripts/start.sh` 和 `bash scripts/stop.sh`。如果要让 N100 重启后自动恢复，使用上面的用户级 systemd 服务。

## 配置

复制 `.env.example` 为 `.env` 后按需设置：

- `APP_PORT`: 后端端口，默认 `8088`
- `OSINT_DB_PATH`: SQLite 数据库路径，默认 `data/osint.sqlite`
- `AGENT_API_TOKEN`: 外部 Agent 写回 API 的 Bearer Token，生产环境建议设置
- `ADMIN_API_TOKEN`: 管理类写操作的 Bearer Token；未设置时回退使用 `AGENT_API_TOKEN`
- `READ_API_TOKEN`: 读取调查、Agent、系统状态等敏感接口的 Bearer Token；生产环境建议与写 token 分离
- `VITE_ADMIN_API_TOKEN`: 前端调用管理类写接口时使用的 Bearer Token；启用 `ADMIN_API_TOKEN` 后前端构建环境也需要设置
- `OSINT_LLM_BASE_URL` / `OSINT_LLM_API_KEY` / `OSINT_LLM_MODEL`: 情报官模型中转配置
- `UPKUAJING_BASE_URL`: 跨境魔方后台地址，默认 `https://saas.upkuajing.com`
- `UPKUAJING_AUTHORIZATION`: 跨境魔方 API 的 `Authorization` 请求头完整值，例如 `Bearer ...`
- `UPKUAJING_TIMEOUT_SECONDS`: 跨境魔方 API 超时时间，默认 `30`
- `SHERLOCK_*`、`THEHARVESTER_*`、`AMASS_*`、`SUBFINDER_COMMAND`、`HTTPX_COMMAND`、`KATANA_COMMAND`、`OFFICIAL_SITE_SEARCH_*`、`SPIDERFOOT_*`、`PHONEINFOGA_*`、`GHUNT_*`、`RECONNG_*`、`COMPANY_NEWS_*`: 本地工具或服务配置

`COMPANY_NEWS_SOURCE=gnews` 会优先尝试 GNews Python 包，缺包时回退到 Google News RSS；如果安装了 Newspaper4k，会对新闻 URL 做正文、摘要、发布日期等解析。

`OFFICIAL_SITE_SEARCH_BASE_URL` 可指向 SearXNG 兼容的 JSON 搜索端点。配置后，`company` 和 `sparse_lead` standard/deep 任务会先搜索官网候选 URL，再递进触发 `httpx`、`katana` 和 `official_site_extractor`。

凭证只放在运行环境或 `.env`，不要写入事件、证据、报告或截图。

<production-host> 当前已验证的 ProjectDiscovery 配置：

```bash
SUBFINDER_COMMAND=<osint-bin>/subfinder
HTTPX_COMMAND=<osint-bin>/httpx
KATANA_COMMAND=<osint-bin>/katana
```

最终域名 quick 实测任务 `<final-domain-task-id>` 已完成：`COMPLETED`，质量分 `78.1 / 100`，`subfinder`、`httpx`、`katana`、`official_site_extractor` 全链路完成，失败和阻断均为 `0`。阶段收尾记录见 [docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md](docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md)。

### 跨境魔方海关 API

后端提供代理接口 `POST /api/customs/trade/list`，请求体与跨境魔方 `POST /customs/trade/list` 保持一致。该代理接口属于管理类写接口，生产环境需要 `ADMIN_API_TOKEN` 或 `AGENT_API_TOKEN` 授权；第三方后台的 `UPKUAJING_AUTHORIZATION` 只保存在服务器环境变量中，不暴露给前端。

直接调用情报官代理：

```bash
curl -sS http://127.0.0.1:8088/api/customs/trade/list \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "seller": "SHANDONG ORIENT ALUMINIUM CO., LTD.",
    "isExact": true,
    "products": [],
    "hscodes": [],
    "sorting_field": "tradeDate",
    "sorting_direction": "desc"
  }'
```

也可以用脚本按公司名拉取并保存原始 JSON：

```bash
UPKUAJING_AUTHORIZATION="Bearer <token>" \
python3 scripts/upkuajing_trade_list.py \
  --seller "SHANDONG ORIENT ALUMINIUM CO., LTD." \
  --date-start 2024-01-01 \
  --date-end 2026-06-24 \
  --output reports/upkuajing/shandong-orient-trades.json
```

接口返回 `data.cursor` 时，可用 `--cursor "<cursor>"` 继续翻页。

## Agent 接入

协议文档见 [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md)。

Agent Mail CLI 的本机安装、授权账号、维护命令和故障排查见 [docs/AGENT_MAIL_CLI_MAINTENANCE.md](docs/AGENT_MAIL_CLI_MAINTENANCE.md)。

真实信息整理必须遵守 [docs/REAL_OSINT_WORKFLOW.md](docs/REAL_OSINT_WORKFLOW.md)：先提取截图/CRM 锚点，再做约束式公开检索，补齐企业名称、官网、邮箱、电话、地址、注册信息、业务范围、贸易信号和决策人候选，最后写入证据账本、事实池、ACH 和 BLUF。工具命中只能作为候选，不能跳过交叉验证直接写成确定事实。

## Agent / Skill 治理层

项目包含一个静态治理层，用于把职责型 Agent 的行为规则从长文档中拆成可复用、可校验的文件：

- `agents/`: 角色 Agent 的规范提示词，例如企业情报、社媒情报、联系方式、交叉验证和分析评价。
- `skills/`: 可复用工作流，例如约束式检索、证据晋级、交叉验证和 BLUF 报告。
- `agent-manifest.json`: 声明 Agent、Skill、允许工具族和输出合同。
- `scripts/check_agents.py`: 检查 manifest、frontmatter 和引用路径是否一致。

这层暂不改变 API、Worker、前端或任务执行逻辑；它用于约束外部 Agent、Codex 会话和未来 MCP/托管 Agent 包装。打包或部署前建议运行：

```bash
python3 scripts/check_agents.py
```

结构化 Agent 写回会在 API 边界做轻量校验：`entities`、`evidence`、`evidence-records`、`facts` 和 `relationships` 必须包含必需字段，置信度必须在 `0..1`，已确认事实必须带证据 ID 和 Admiralty Code。校验失败会返回 `400` 和错误列表。

本地职责 Agent 还按责任分为 reader / verifier / reporter 三层：采集类角色只能写实体、证据和关系；交叉验证角色负责事实、假说和评分；分析评价角色只负责报告和任务完成。这是应用层责任隔离，不是 OS 级沙箱。

项目还提供 MCP-style discovery layer：`/api/mcp/descriptor` 会暴露只读工具、资源和提示词描述，`/api/mcp/resources/agent-manifest` 与 `/api/mcp/resources/intel-schema` 可供外部运行时读取治理层和情报 schema。它不是完整 MCP JSON-RPC server，当前不开放远程写入工具。

典型流程：

```bash
cd /path/to/osint-agent-network

PYTHONPATH=backend python3 -m app.agent_client register \
  --agent-name codex-desktop \
  --agent-type codex \
  --capability company \
  --capability domain \
  --capability email

PYTHONPATH=backend python3 -m app.agent_client claim \
  --agent-id <agent-id> \
  --capability company
```

外部 Agent 写回时必须同时写实体、证据和关系。任何结论都要能追溯到 `source_tool` 和 `evidence`。

执行底层工具前，先通过中枢规划路线：

```bash
PYTHONPATH=backend python3 -m app.agent_client plan-tools \
  --target-type domain \
  --target example.com \
  --strategy deep
```

当工具结果产生新的邮箱、电话、官网、新闻 URL 或社媒主页时，Worker 会按策略预算继续派生后续 job。派生任务的 `depends_on` 会记录为 `inferred_from:<entity_type>:<entity_value>`，用于前端队列、事件日志、图谱证据线和最终报告追溯。

处理 Alibaba/CRM 空白 Lead 时，Agent 必须先提取截图锚点，例如完整姓名、姓名变体、国家、买家等级、注册/建档/咨询时间、业务员、采购品类和年采购额；再用约束式检索做公开来源补全。候选公司事实和“是否属于这个买家”的身份匹配置信度必须分开标注。

## 验证

后端单元测试：

```bash
cd /path/to/osint-agent-network
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_agent_protocol backend.tests.test_worker backend.tests.test_graph
```

前端检查：

```bash
cd /path/to/osint-agent-network/frontend
npm run check:ui-copy
node --experimental-strip-types ./scripts/test-ui-state.ts
node --experimental-strip-types ./scripts/test-graph-helpers.ts
node --experimental-strip-types ./scripts/test-investigation-bundle.ts
npm run build
```

也可以直接运行项目包验证脚本：

```bash
cd /path/to/osint-agent-network
bash scripts/verify.sh
```

稳定性运维：

```bash
bash scripts/backup.sh
bash scripts/healthcheck.sh
python3 scripts/regression_smoke.py
python3 scripts/production_readiness.py
python3 scripts/runtime_inventory.py
```

`backup.sh` 会备份 `data/`、`reports/` 和 `.env` 快照，默认保留最近 14 份，可用 `BACKUP_KEEP_LAST` 调整；`healthcheck.sh` 会检查 API、系统自检接口、数据库状态、备份脚本和 Web 页面。`regression_smoke.py` 使用固定样本验证 PIR/EEI、交叉验证矩阵和 BLUF/I&W 报告结构。`production_readiness.py` 汇总 API、Web、数据库、工具健康、生产 Token 和备份 timer，适合作为 <production-host> 成熟版本验收命令；`runtime_inventory.py` 统计本地数据库、截图、报告和 job artifact，公开发布前必须复核。真实 OSINT 工具按需启用，不要求默认常驻后台。

UI 人工验收：

- 打开 `http://127.0.0.1:3008/`
- 选择 `美国企业背调：Sample Hospitality LLC / Sample Contact`
- 检查队列中有企业情报、社媒情报、联系方式、上下游、采购意图、交叉验证、分析评价 Agent
- 检查图谱有 5 个顶部证据、5 个底部证据、中间核心节点、左右企业/决策人信息块
- 检查连线为很细彩线，结论能看到来源链

## 项目文档

- [DESIGN.md](DESIGN.md): UI 视觉与交互规则
- [docs/UPDATE_LOG.md](docs/UPDATE_LOG.md): 更新日记、修复摘要和 <production-host> 部署记录
- [docs/AGENT_PROTOCOL.md](docs/AGENT_PROTOCOL.md): Agent API、写回协议、工具适配器
- [docs/INTEL_GATEWAY.md](docs/INTEL_GATEWAY.md): 情报工具中枢、路线矩阵、配置跳过规则
- [docs/ORCHESTRATION_MODEL.md](docs/ORCHESTRATION_MODEL.md): 多 Agent 编排、职责分工、数据流
- [docs/GRAPH_TEMPLATE.md](docs/GRAPH_TEMPLATE.md): 23 位图谱模板和证据关系标准
- [docs/PROJECT_PACKAGE.md](docs/PROJECT_PACKAGE.md): 成熟项目包、部署、运维、验收清单
- [docs/TEMPORARY_CLOSURE_2026-07-06.md](docs/TEMPORARY_CLOSURE_2026-07-06.md): 当前阶段临时收尾、验证证据和剩余可选工作
- [docs/N100_DEPLOYMENT_RUNBOOK.md](docs/N100_DEPLOYMENT_RUNBOOK.md): <production-host> 部署、systemd、烟测、备份和回滚 Runbook
- [docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md](docs/N100_ACTUAL_TEST_CLOSURE_REPORT_2026-07-06.md): 2026-07-06 <production-host> 实际任务测试、修复、复测和收尾报告
- [docs/REAL_TOOL_ENABLEMENT.md](docs/REAL_TOOL_ENABLEMENT.md): <production-host> 真实 OSINT 工具接线、缺口和验收清单
- [docs/FINAL_HANDOFF.md](docs/FINAL_HANDOFF.md): 最终交付摘要、运行边界和后续增强项
- [docs/DEVELOPMENT_MANUAL.md](docs/DEVELOPMENT_MANUAL.md): 开发手册和早期规划记录
- [docs/PUBLIC_RELEASE_READINESS.md](docs/PUBLIC_RELEASE_READINESS.md): 公开仓库发布前的 GPLv3、凭证、运行数据和验证门禁
- [docs/PUBLIC_REPOSITORY_MAINTENANCE.md](docs/PUBLIC_REPOSITORY_MAINTENANCE.md): 公开仓库隐私痕迹、占位符和发布前扫描维护规则
- [docs/OPEN_SOURCE_LICENSE_OPTIONS.md](docs/OPEN_SOURCE_LICENSE_OPTIONS.md): GPLv3 选择记录、SPDX 标识和发布注意事项

## 当前成熟度

项目已经具备部署闭环：任务创建、Agent 队列、SQLite 可恢复后台 worker 队列、工具适配器协议、SQLite 持久化、情报循环调度、交叉验证、图谱展示、白皮书报告、质量闸门、Token 保护、验证脚本和 <production-host> systemd Runbook。当前公开发布协议已经固定为 GNU GPL v3 (`GPL-3.0-only`)。下一步最值得继续增强的是更多真实工具产物样本、PDF/HTML 导出模板、权限分层和审计日志。
