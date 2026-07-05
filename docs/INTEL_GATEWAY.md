# 情报工具中枢

Version: 0.1
Updated: 2026-05-20

情报工具中枢是 Agent 与底层 OSINT 工具之间的稳定路由层。Agent 不应该直接根据工具清单盲目全跑，而是先把目标类型、目标值和策略交给中枢，由中枢返回应该执行的工具路线、跳过原因、输出合同和职责角色。

## 目标

- 稳定：只给当前目标调用合适工具，避免工具越多结果越乱。
- 可解释：每个路线都带 `source_tier`、`output_contract` 和可展示的 `skip_reason`。
- 可配置：需要服务或凭证的工具，缺配置时自动跳过，不阻断整体任务。
- 可扩展：新增工具先注册能力，再加入路线矩阵，Agent 调用方式不变。

## Agent 调用顺序

1. 调用中枢规划路线。
2. 按 `routes` 顺序执行工具或分派职责型 Agent。
3. 工具产物统一解析为 `entities`、`evidence`、`relationships`。
4. 交叉验证 Agent 合并重复、标注冲突和来源等级。
5. 红队/分析评价 Agent 使用 ACH 与 I&W 征候矩阵形成预测判断。
6. 分析评价 Agent 按 BLUF 把成熟结论写入图谱槽位和报告。

CLI 示例：

```bash
PYTHONPATH=backend python3 -m app.agent_client plan-tools \
  --target-type email \
  --target buyer@example.com \
  --strategy standard
```

API 示例：

```http
GET /api/tools/plan?target_type=domain&target=example.com&strategy=deep
```

返回结构：

```json
{
  "target_type": "domain",
  "target_value": "example.com",
  "strategy": "deep",
  "routes": [
    {
      "tool_name": "theharvester",
      "target_type": "domain",
      "target_value": "example.com",
      "priority": 1,
      "agent_role": "tool_agent",
      "output_contract": "entities,evidence,relationships",
      "depends_on": "",
      "source_tier": "domain_discovery",
      "skip_reason": ""
    }
  ],
  "skipped_routes": []
}
```

## 路线矩阵

| Target Type | 默认路线 | 说明 |
| --- | --- | --- |
| `username` | Sherlock -> Maigret -> socialscan | 先确认账号存在，再提取资料档案和跨平台命中 |
| `email` | socialscan -> SpiderFoot -> Recon-ng -> GHunt | GHunt 只有配置 Cookie 后进入路线 |
| `phone` | PhoneInfoga | 电话目标只跑电话工具，避免无效扩散 |
| `domain` | theHarvester -> Amass -> SpiderFoot -> Recon-ng | 域名只走基础设施、邮箱和被动富集，不跑社媒工具 |
| `subdomain` | Amass -> SpiderFoot | 子域名聚焦 DNS 和被动事件 |
| `profile_url` | Profile Parser | 主页 URL 只做页面资料解析 |
| `company` | Company News + 职责型 Agent 队列 | 企业、社媒、联系方式、上下游、采购意图、新闻动态、交叉验证、分析评价 |

`quick` 策略会缩短路线，只保留低成本工具。`standard`、`deep`、`maximum` 按矩阵完整规划，但仍受配置健康检查约束。

## 配置跳过规则

| 工具 | 必要配置 | 缺失时 |
| --- | --- | --- |
| SpiderFoot | `SPIDERFOOT_BASE_URL` | 路线进入 `skipped_routes`，原因 `missing_config:SPIDERFOOT_BASE_URL` |
| Recon-ng | `RECONNG_COMMAND` | 路线进入 `skipped_routes`，原因 `missing_config:RECONNG_COMMAND` |
| GHunt | `GHUNT_COOKIE_PATH` | 路线进入 `skipped_routes`，原因 `missing_config:GHUNT_COOKIE_PATH` |

PhoneInfoga、Sherlock、Maigret、socialscan、theHarvester、Amass 仍由具体适配器在执行时检查命令或服务状态。Worker 遇到缺命令会把 job 标为 `BLOCKED` 并写事件。

## Company 任务

企业类任务不把 Sherlock、Maigret、SpiderFoot、Recon-ng 等原始工具全部直接压上去，而是生成职责型 job：

- `company_osint` -> `enterprise_intel_agent`
- `social_profile_search` -> `social_intel_agent`
- `contact_discovery` -> `contact_discovery_agent`
- `supply_chain_mapping` -> `supply_chain_agent`
- `purchase_intent_assessment` -> `purchase_intent_agent`
- `company_news` -> `tool_agent`
- `company_news_monitoring` -> `news_intel_agent`
- `cross_verification` -> `cross_verification_agent`
- `analysis_judgement` -> `analysis_judgement_agent`

职责型 Agent 可以在自己的工作流内调用工具中枢或人工搜索，但写回任务中心时必须遵守实体、证据、关系标准协议。

## 递进式推演闭环

工具中枢不只负责第一轮工具选择，也负责把已经确认或半确认的实体转化为下一步动作。核心原则是：从强线索继续追，不从泛名乱搜；预测下一步是队列计划，不是事实结论。

标准闭环：

1. `tool_agent` 或职责型 Agent 写回 `entities`、`evidence`、`relationships`。
2. Worker 从新实体中提取高价值线索。
3. 调用 `plan_progressive_jobs` 生成下一批工具任务。
4. 新 job 的 `depends_on` 写入 `inferred_from:<entity_type>:<entity_value>`，用于队列、事件、图谱和报告追溯。
5. 后续工具结果再次写回实体、证据、关系。
6. 交叉验证 Agent 判断哪些信息成熟，分析评价 Agent 再写入图谱主槽位和报告。

高价值线索到下一步动作：

| 新发现实体 | 下一步动作 | 目的 |
| --- | --- | --- |
| `domain` / 官网域名 | theHarvester、Amass、SpiderFoot、Recon-ng | 提取邮箱、子域名、页面、基础设施和公开联系人 |
| `email` | socialscan、SpiderFoot、Recon-ng，并派生 username/domain | 反查账号足迹、域名组织关系、联系人归属 |
| `phone` | PhoneInfoga | 查公开电话足迹和可能关联页面 |
| `profile_url` / 高价值 `external_link` | Profile Parser，并提取域名 | 抽取简介、位置、链接、兴趣、照片 URL 等公开资料 |
| `news_article` / 新闻 URL | Profile Parser / 新闻正文解析 | 抽取新闻事实、项目、合作、采购或风险信号 |
| `organization` / `company` | Company News + 企业职责型队列 | 补充新闻、官网、联系方式、上下游、采购意图 |

示例：如果官网上提取到企业电话和邮箱，系统应先写入：

```text
entity(phone) + evidence(contact_page) + relationship(company_has_phone)
entity(email) + evidence(contact_page) + relationship(company_has_email)
```

然后再基于电话、邮箱、域名分别规划 PhoneInfoga、socialscan、theHarvester/Amass 等后续任务。后续任务只能说明“需要验证这条线索”，不能直接把反查结果写成成熟结论。

## IntelCore 预测层

企业类 `deep` / `maximum` 任务中，职责型队列要支持前瞻性分析：

- `cross_verification_agent` 输出 `admiralty_code`、来源等级、冲突和噪声检查。
- `analysis_judgement_agent` 输出 `PIR`、`ACH`、`BLUF`、`estimative_language`、`directed_collection`。
- `news_intel_agent` 和 `purchase_intent_agent` 应把新闻、采购、营销、招聘、物流、供应链变化转成 I&W 征候。

I&W 征候矩阵推荐字段：

```json
{
  "target_action": "可能的下一步动作",
  "time_window": "未来 14-21 天",
  "triggered_indicators": ["IND_SUPPLY_CHAIN", "IND_MARKETING_TEST"],
  "indicator_activation_rate": 0.72,
  "confidence_language": "很有可能",
  "admiralty_code": "B-2"
}
```

ACH 输出推荐字段：

```json
{
  "hypothesis": "扩大采购并压价",
  "supporting_evidence": ["..."],
  "contradictory_evidence": ["..."],
  "status": "MOST_LIKELY"
}
```

系统可以输出行动建议，但不自动执行欺骗、投放、反情报或干扰类动作。

## 企业新闻工具

`company_news` 是第 10 个底层工具，负责按企业名称发现企业新闻并结构化输出：

- 新闻发现：优先 GNews Python 包，缺包时回退 Google News RSS。
- 正文解析：如果安装 Newspaper4k，则对新闻 URL 提取标题、正文摘要、发布时间、作者和主图。
- 输出实体：`news_article`、`news_summary`、`published_at`、`external_link`。
- 输出证据：`company_news_report`、`news_business_event`、`news_buying_signal`、`news_risk_signal`。
- 输出关系：`company_has_news_article`、`news_supports_business_event`、`news_supports_buying_signal`、`news_supports_risk_signal`。

它不是常驻爬虫，只在任务执行时按需查询一次，适合 n100 的轻量使用模式。

## 约束式检索方法

任何 Agent 调用搜索、新闻或社媒工具前，必须先从已确认信息中提取检索约束，不能直接用单一泛名搜索。

### 1. 提取已确认字段

按证据强弱整理字段：

- 核心主体：企业名称、决策人姓名、用户名、邮箱、电话、官网。
- 地区约束：国家、城市、经营地址、活动地区。
- 平台约束：Alibaba、LinkedIn、Facebook、Instagram、企业官网、行业目录等。
- 业务约束：采购品类、主营业务、行业、供应商、进口、项目、询盘。
- 时间约束：注册时间、建档时间、新闻发布时间、近期活动窗口。
- 排除词：同名人物常见噪声，例如 sport、football、soccer、music、composer、crime、prison 等。

### 2. 组合查询矩阵

检索应从强约束到弱约束逐层放宽：

```text
"精确姓名/企业名" + 地区
"精确姓名/企业名" + 平台
"精确姓名/企业名" + 业务/采购语境
"备用姓名/企业名" + 地区 + 平台
"备用姓名/企业名" + 地区 + company/import/purchase/supplier
官网/邮箱/电话 + 企业名
```

示例：

```text
"David MurilloSoto" Colombia
"David MurilloSoto" Alibaba
"David MurilloSoto" buyer
"David Murillo" Colombia Alibaba buyer
"David Murillo" Colombia import purchasing
"David Murillo" Colombia company
```

### 3. 命中结果判断

搜索结果必须满足至少一个条件才可写入主图谱：

- 同时命中精确主体和地区/平台/业务约束。
- 命中备用主体，但有两个以上其他字段交叉支持。
- 来源为 A/B 级，且内容明确指向同一企业或同一决策人。

以下结果只能进入待复核或直接丢弃：

- 只命中普通姓名，没有地区、平台、业务或联系方式约束。
- 明显同名人物，例如运动员、音乐人、刑事新闻、娱乐新闻。
- 聚合站摘要无法打开或无法找到原文。
- 结果只包含宽泛关键词，不能支持任何实体或关系。

### 4. 工具执行要求

- `company_news` 必须优先使用带地区、平台和业务语境的查询；泛名结果不得自动写入主结论。
- `social_profile_search` 必须优先使用精确用户名/姓名 + 地区/公司约束。
- `contact_discovery` 必须把个人联系方式和企业联系方式分开，不能混写。
- `analysis_judgement_agent` 必须解释每条成熟结论来自哪些约束和证据。

## 质量标准

- 每个实体必须能追溯到 `source_tool`。
- 每条证据必须能说明来源类型或证据片段。
- 关系必须表达方向，例如 `company_has_phone`、`email_has_profile`、`domain_has_subdomain`。
- 每个递进生成的 job 必须保留 `depends_on=inferred_from:...`，说明它由哪条线索触发。
- 单一弱来源不得直接成为成熟结论；进入折叠区或待复核。
- 成熟结论优先来自 A 级来源，或两个以上 B/C 来源交叉支持。
