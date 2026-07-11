# Agent Protocol

Version: 0.3
Base URL: `http://127.0.0.1:8088`

This project treats the web UI as a display board. Execution is done by external agents such as Codex Desktop, OpenHuman on <production-host>, or any CLI agent that can make HTTP requests.

Each external Agent uses the token returned once by administrator-authorized registration. Every `/api/agent/*` request must include:

```http
Authorization: Bearer <issued-agent-token>
```

`POST /api/agents/register` requires `ADMIN_API_TOKEN`; it never accepts a shared Agent token as a registration credential. The legacy `AGENT_API_TOKEN` path is disabled by default and production startup/readiness reject `OSINT_ALLOW_LEGACY_AGENT_TOKEN=true`.

## Roles

- Web UI: display tasks, agents, events, entities, evidence, relationships, and reports.
- API: store task state and evidence written by agents.
- Worker: execute local `tool_agent` jobs and write normalized tool output back.
- Agent: claim tasks, run tools or research workflows, make decisions, cross-verify findings, and write results back.
- Intel Tool Gateway: plan which underlying tools should run for a target before an Agent or Worker executes them.

For `company` investigations, the system creates role-based orchestration jobs. These jobs are visible in the UI and are intended for specialized external agents:

| Agent role | Job name | Responsibility |
| --- | --- | --- |
| `enterprise_intel_agent` | `company_osint` | 企业主体、官网、基础联系方式、地址、主营业务 |
| `social_intel_agent` | `social_profile_search` | 社媒主页、简介、位置、关联链接、公开兴趣线索 |
| `contact_discovery_agent` | `contact_discovery` | 企业电话、企业邮箱、决策人公开联系方式 |
| `supply_chain_agent` | `supply_chain_mapping` | 上游、下游、合作伙伴、同址企业、行业邻近对象 |
| `purchase_intent_agent` | `purchase_intent_assessment` | 采购品类、需求匹配、采购阶段、购买信号 |
| `news_intel_agent` | `company_news_monitoring` | 企业新闻、企业动态、公开报道中的采购或风险信号 |
| `cross_verification_agent` | `cross_verification` | 冲突检查、来源等级、重复合并、置信度调整 |
| `analysis_judgement_agent` | `analysis_judgement` | 成熟画像、买家评分、风险摘要、图谱槽位和报告 |

The local worker skips non-`tool_agent` jobs and records an event saying the job is waiting for a responsible Agent.

## Tool Planning

Agents should ask the Intel Tool Gateway for routes before running low-level tools. This keeps tool use stable as the number of adapters grows.

`GET /api/tools/plan?target_type=email&target=buyer@example.com&strategy=standard`

CLI equivalent:

```bash
PYTHONPATH=backend python3 -m app.agent_client plan-tools \
  --target-type email \
  --target buyer@example.com \
  --strategy standard
```

The response contains executable `routes` and non-fatal `skipped_routes`. A skipped route includes `skip_reason`, for example `missing_config:GHUNT_COOKIE_PATH`.

## Constrained Search Method

Before using search, news, or social tools, Agents must build a constrained query from confirmed fields. Do not search a single broad name and write the results as facts.

Required workflow:

1. Extract confirmed fields from the task: exact name, alternate name, company name, country/region, platform, website, email, phone, industry, purchase category, dates.
2. Build queries from strong to weak constraints:
   - `"exact name" + country/region`
   - `"exact name" + platform`
   - `"exact name" + buyer/purchase/import/supplier/company`
   - `"alternate name" + country/region + platform`
   - `"alternate name" + country/region + business context`
3. Add exclusion logic for obvious same-name noise such as sport, football, soccer, composer, music, crime, prison, entertainment, or unrelated public figures.
4. Write a result to the main graph only if it matches the subject plus at least one independent constraint, or if two weaker sources cross-confirm the same entity/relationship.
5. Put broad same-name hits into review notes or discard them. Do not turn them into `news_article`, `social_profile`, or `risk_signal` conclusions.

For example, a lead with `David MurilloSoto`, `David Murillo`, `Colombia`, and `Alibaba buyer` should search:

```text
"David MurilloSoto" Colombia
"David MurilloSoto" Alibaba
"David MurilloSoto" buyer
"David Murillo" Colombia Alibaba buyer
"David Murillo" Colombia import purchasing
"David Murillo" Colombia company
```

Results about athletes, composers, crime reports, or unrelated public figures must not be written as confirmed intelligence unless another strong field ties them back to the buyer lead.

## Alibaba Blank Lead SOP

When the input is a sparse Alibaba/CRM lead profile, Agents must use this SOP before treating the lead as a low-value record. A blank lead is a profile with few or no fields such as email, phone, company website, purchase category, annual amount, and business type.

When the operator can enter screenshot anchors directly, create the task as `seed_type=sparse_lead` and put platform, display name, member ID, country, raw company field, categories, and RFQs in investigation metadata. Agents must write those anchors before public candidate discovery.

### Anchors

Extract every confirmed anchor first:

- `exact_name`: full visible buyer/account name, including Latin compound surname such as `MurilloSoto` or `Murillo Soto`.
- `company_name_raw`: the visible CRM/company-name field exactly as shown. Treat this as an enterprise, trade name, or natural-person merchant anchor first, even if the text looks like a personal name.
- `alternate_name`: shortened or spaced variants, for example `David Murillo`. Do not create this from a company field unless it is explicitly labeled as a name variant.
- `country_region`: flag, address country, activity region.
- `platform_context`: Alibaba buyer page, TM inquiry, CRM source, buyer level.
- `timestamps`: registration time, lead creation time, latest inquiry time, and local-time conversion.
- `sales_context`: salesperson, chat source, business card request status, visible purchase category, annual amount.

Write these anchors as entities/evidence before external search. Screenshot-derived platform facts can be strong for “this CRM record exists,” but not for “this buyer belongs to a public company.”

Field labels have priority over text interpretation. If `David Murillo` appears under `company_name_raw`, Agents must search it as a company/trade-name/natural-person merchant first: `David Murillo empresa`, `David Murillo RUES`, `David Murillo NIT`, `David Murillo cámara de comercio`, and only then consider person-profile candidates. Keep the CRM company field, buyer account name, public company record, and decision-maker identity as separate graph nodes until evidence closes them.

### Trace Hunting

Search from strongest to weakest:

```text
"full compound name" + country
"full compound name" + Alibaba / buyer / import / purchasing
"full compound name" + LinkedIn
"alternate name" + country + business context
"alternate name" + country + LinkedIn + industry
"alternate name" + country + company registry / RUES / NIT
"company_name_raw" + country + company registry / RUES / NIT
"company_name_raw" + empresa / cámara de comercio / dirección / teléfono
```

For Latin American leads, compound surname variants are high-value disambiguators. Try joined, spaced, hyphenated, and accent-safe variants:

```text
David MurilloSoto
David Murillo Soto
David Murillo-Soto
```

Do not promote a broad `first_name + surname` hit unless it also matches country, platform, company, industry, email, phone, avatar, or another independent anchor.

When a company-field value looks like a personal name, separate these confidence scores:

- `record_confidence`: whether the public record is real.
- `identity_match_confidence`: whether that public record belongs to this Alibaba lead.
- `field_interpretation_confidence`: whether the CRM field is best interpreted as company name, trade name, natural-person merchant, or personal name mistakenly entered in the company field.

### Public Business Corroboration

If a candidate company appears, enrich it through public and authorized sources:

- Official website and contact page.
- Local registry or business directory, for Colombia including public RUES/NIT-style records when available.
- Company directory pages such as chambers, ConnectAmericas, industry associations, maps, and B2B profiles.
- Public import/export signals or paid/authorized bill-of-lading sources, if available to the operator.
- Product/HS-code fit, for example aluminum profiles `7604`, tempered glass `7007`, doors/windows, handrails, machinery, or the relevant product family.

Customs/import information must be labeled by source type. If it comes from a paid commercial database or operator-provided export, mark it as that source; do not imply official confirmation unless it is actually official.

### Intent Evaluation

Evaluate purchase intent using both platform facts and behavior:

- Alibaba buyer level such as `L3`.
- Lead creation time converted to buyer local work hours.
- TM inquiry context and whether it happened during business hours.
- Visible purchase category, annual amount, recent search terms, browsing trail, inquiry products, and chat content.
- Willingness to provide drawings/specs, target quantity, destination, standards, and timeline.

Buyer level and business-hour inquiry are useful intent signals, but they do not prove purchase category or company identity by themselves.

### Red-Team Scenarios

For sparse Alibaba leads, the report should include at least three scenarios:

- `Alpha / Most likely`: real B2B buyer comparing suppliers for a live project or replacement supply chain.
- `Beta / Most dangerous`: buyer uses the quote to pressure an incumbent supplier or benchmark the market.
- `Gamma / Noise`: same-name or personal account with insufficient company/procurement evidence.

Use I&W indicators to separate the scenarios:

- Provides drawings/specifications, destination, quantity, timeline: strengthens Alpha.
- Avoids company identity and only asks generic price/MOQ: strengthens Beta.
- Search results cannot connect name to company/contact/product: strengthens Gamma.

### Allowed Follow-Up

Business follow-up recommendations may ask the salesperson to request missing facts in a transparent way, for example company name, website, WhatsApp, drawings, project location, target quantity, and product standard. Do not describe this as automated deception or covert probing. The system may recommend wording, but it must remain ordinary sales qualification.

### Graph Placement

Main graph slots should show:

- Confirmed Alibaba/CRM anchors.
- Candidate company and candidate decision-maker profile only if clearly marked as candidate.
- Contact, website, business scope, upstream/downstream, and purchase intent only with source lines.
- Unknown fields as `待补充`, not invented values.

## Progressive Inference Method

Agents should treat each confirmed clue as a possible next action. This is similar to an analyst asking “what should be checked next?” after every useful observation.

Required workflow:

1. Write the newly found clue as an entity.
2. Write evidence that explains where it came from.
3. Write a directional relationship tying it to the company, person, website, article, or profile.
4. Ask the Intel Tool Gateway or local worker planner for follow-up jobs.
5. Mark every inferred follow-up with `depends_on=inferred_from:<entity_type>:<entity_value>`.
6. Run the follow-up only if it fits the strategy budget and does not duplicate an existing `tool_name + target_type + target_value`.
7. Keep predicted next steps separate from mature conclusions until cross-verification finishes.

Recommended inference map:

| Entity | Follow-up | Notes |
| --- | --- | --- |
| `domain` / official website | domain discovery and passive enrichment | Find emails, subdomains, pages, public contacts. |
| `email` | socialscan, passive enrichment, username/domain derivation | Verify ownership before linking to a decision maker. |
| `phone` | PhoneInfoga | Keep company phone and personal phone separated. |
| `profile_url` / high-value `external_link` | Profile Parser | Extract public bio, location, image URL, links, interests. |
| `news_article` | article/profile parsing and news claim extraction | A news hit is evidence for a claim, not a confirmed claim by itself. |
| `organization` / `company` | company news and role-based company jobs | Enrich website, contacts, supply chain, purchase intent. |

Example evidence chain:

```text
official website -> contact page evidence -> company email -> inferred email follow-up -> social/account result -> cross verification -> graph slot
```

The UI queue may display `depends_on` so the operator can see why a job exists. If a follow-up returns weak or noisy information, it should remain a review note rather than filling the main graph.

## Task Lifecycle

- `OPEN`: task is available for any capable agent.
- `CLAIMED`: an agent has claimed the task.
- `RUNNING`: the agent has started writing events or results.
- `NEEDS_REVIEW`: the agent finished but wants human review.
- `COMPLETED`: finished successfully.
- `PARTIAL_FAILED`: some tools failed but useful results exist.
- `FAILED`: execution failed.
- `CANCELLED`: task was cancelled.
- `STALE_CLAIM`: the claim expired and may be reclaimed.

## Target Types

Supported target types:

- `company`: company or buyer organization name.
- `sparse_lead`: weak Alibaba/CRM/platform buyer lead with multiple visible anchors but no confirmed company, email, phone, or domain.
- `domain`, `subdomain`, `ip`: infrastructure and web assets.
- `email`, `username`, `phone`: identity and contact clues.
- `url`, `profile_url`: public web pages and social profiles.

`phone` targets must use E.164 format such as `+12125550123`.

`company` targets preserve human-readable names and are normalized by trimming repeated spaces.

## Register Agent

`POST /api/agents/register`

```json
{
  "agent_name": "codex-desktop",
  "agent_type": "codex",
  "capabilities": ["company", "domain", "username", "email", "sherlock", "theharvester", "amass"],
  "role_tier": "reader"
}
```

Allowed tiers are `reader`, `verifier`, `reporter`, and `tool_agent`. They are explicit, non-hierarchical contracts: collection writes require `reader`, confirmed facts and hypotheses require `verifier`, final completion/report writes require `reporter`, and atomic tool output requires `tool_agent`. Register separate identities when one runtime needs more than one contract.

Response:

```json
{
  "id": "agent-uuid",
  "agent_name": "codex-desktop",
  "agent_type": "codex",
  "capabilities": ["domain", "username"],
  "role_tier": "reader",
  "agent_token": "<redacted>",
  "status": "ONLINE",
  "registered_at": "2026-05-19T00:00:00+00:00",
  "last_seen_at": "2026-05-19T00:00:00+00:00"
}
```

Store `agent_token` immediately in that Agent's secret runtime environment; the API persists only its hash and never returns the plaintext again. Re-registering the same stable `agent_name` rotates the token, updates tier/capabilities, and invalidates the old token immediately. This is also the migration path for legacy agents. Do not put the token in events, evidence, reports, screenshots, shell history, or source-controlled files.

Authorization outcomes:

- `401 Unauthorized`: missing, malformed, unknown, rotated, or disabled Agent credential. Re-register/rotate through an administrator when appropriate.
- `403 Forbidden`: the credential is known but the body `agent_id`, `role_tier`, registered capability, action, or management/Agent credential class is not permitted.
- `409 Conflict`: the task/Job is not actively owned by this exact Agent, has been released/closed, or the requested output is outside the active claim contract. Refresh state and obtain a current claim instead of replaying the mutation.

## Heartbeat

`POST /api/agents/heartbeat`

Heartbeat remains a management write route: use an authenticated administrator browser session or `ADMIN_API_TOKEN`. The issued Agent token is scoped to `/api/agent/*` claim/write routes and is not accepted for this plural management endpoint.

```json
{
  "agent_id": "agent-uuid"
}
```

## Claim Task

`POST /api/agent/tasks/claim`

```json
{
  "agent_id": "agent-uuid",
  "capabilities": ["domain", "theharvester", "amass"]
}
```

Response when a task is available:

```json
{
  "task": {
    "id": "task-uuid",
    "name": "example.com 深度调查",
    "seed_type": "domain",
    "seed_value": "example.com",
    "strategy": "deep",
    "status": "CLAIMED",
    "max_depth": 5,
    "max_jobs": 250,
    "max_entities": 2500
  }
}
```

Response for a `company` task includes orchestration jobs:

```json
{
  "task": {
    "id": "task-uuid",
    "name": "Family Hospitality LLC 企业背调",
    "seed_type": "company",
    "seed_value": "Family Hospitality LLC",
    "strategy": "deep",
    "status": "CLAIMED",
    "jobs": [
      {
        "tool_name": "company_osint",
        "target_type": "company",
        "target_value": "Family Hospitality LLC",
        "status": "QUEUED",
        "agent_role": "enterprise_intel_agent",
        "output_contract": "entities,evidence,relationships: company_name, website, phone, email, address, business_scope",
        "depends_on": ""
      },
      {
        "tool_name": "analysis_judgement",
        "target_type": "company",
        "target_value": "Family Hospitality LLC",
        "status": "QUEUED",
        "agent_role": "analysis_judgement_agent",
        "output_contract": "claims,graph_slots,report: buyer_rating, risk_summary, followup_recommendation, mature_profile",
        "depends_on": "cross_verification"
      }
    ]
  }
}
```

Response when no matching task exists:

```json
{
  "task": null,
  "message": "no matching open task"
}
```

## Write Event

`POST /api/agent/events`

```json
{
  "task_id": "task-uuid",
  "agent_id": "agent-uuid",
  "level": "info",
  "message": "开始运行 theHarvester",
  "metadata": {
    "tool": "theharvester",
    "command": "theHarvester -d example.com -b all"
  }
}
```

## Write Entities

`POST /api/agent/entities`

```json
{
  "task_id": "task-uuid",
  "entities": [
    {
      "type": "subdomain",
      "value": "vpn.example.com",
      "source_tool": "amass",
      "confidence": 0.72
    }
  ]
}
```

Entity types should use canonical values such as:

- Company: `organization`, `company`, `brand`, `business_scope`, `declared_location`, `likely_activity_region`.
- Decision maker: `identity`, `real_name`, `bio_snippet`, `gender_claim`, `age_range`, `public_personal_attribute`.
- Contact: `email`, `phone`, `domain`, `url`, `profile_url`, `external_link`.
- Social: `username`, `social_profile`, `platform_account`, `interest_tag`, `declared_location`.
- Evidence-only: `snippet`, `dns_record`, `whois_record`, `risk_signal`.

Use `organization` for graph template slots that should appear as enterprise, partner, upstream, or downstream nodes.

## Write Evidence

`POST /api/agent/evidence`

```json
{
  "task_id": "task-uuid",
  "entity_value": "vpn.example.com",
  "evidence_kind": "dns_resolution",
  "source_tool": "amass",
  "snippet": "A record resolved to 1.2.3.4"
}
```

Evidence snippets should be short, source-specific, and safe to display. Do not include API keys, cookies, raw private tokens, or unrelated personal data.

## Write Relationship

`POST /api/agent/relationships`

```json
{
  "task_id": "task-uuid",
  "from": "example.com",
  "to": "vpn.example.com",
  "relationship_type": "domain_has_subdomain",
  "confidence": 0.8
}
```

Recommended relationship types for enterprise and decision-maker graphing:

- `person_represents_company`
- `person_has_contact`
- `person_has_social_profile`
- `profile_mentions_company`
- `company_has_website`
- `company_has_phone`
- `company_has_email`
- `company_has_business_scope`
- `company_operates_in_region`
- `company_has_partner`
- `company_has_supplier`
- `company_has_customer_type`
- `company_has_purchase_intent`
- `company_has_news_article`
- `news_supports_business_event`
- `news_supports_buying_signal`
- `news_supports_risk_signal`
- `evidence_supports_claim`

Relationship confidence should reflect the evidence chain, not just whether the text was found.

## Complete Task

`POST /api/agent/tasks/{task_id}/complete`

```json
{
  "agent_id": "agent-uuid",
  "status": "COMPLETED",
  "summary": "发现 42 个子域名、8 个邮箱、12 个平台足迹。",
  "report_markdown": "# OSINT 报告\n\n...",
  "confidence": 0.81
}
```

For `analysis_judgement_agent`, the final report should include:

- 企业基础信息。
- 决策人画像。
- 联系方式和来源。
- 主营业务与行业判断。
- 上下游/合作伙伴。
- 采购意图和需求匹配。
- 风险与冲突点。
- PIR 优先情报需求回答。
- Admiralty Code 来源可靠度/信息可信度。
- ACH 竞争性假设分析。
- I&W 征候矩阵和点亮率。
- BLUF 结论先行摘要。
- 定向采集计划。
- 下一步跟进建议。

If important data is missing, write `待补充` or `未在公开来源中确认` rather than inventing fields.

## Minimal Curl Flow

```bash
curl -sS -X POST "http://127.0.0.1:8088/api/agents/register" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <admin-token>' \
  -d '{"agent_name":"cli-agent","agent_type":"cli","role_tier":"reader","capabilities":["domain","amass"]}'

curl -sS -X POST "http://127.0.0.1:8088/api/agent/tasks/claim" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <issued-agent-token>' \
  -d '{"agent_id":"<agent-id>","capabilities":["domain","amass"]}'

curl -sS -X POST "http://127.0.0.1:8088/api/agent/events" \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer <issued-agent-token>' \
  -d '{"task_id":"<task-id>","agent_id":"<agent-id>","level":"info","message":"开始执行","metadata":{}}'
```

## Standard CLI Flow

外部 Agent 可以直接使用后端内置 CLI，不必手写 `curl`。默认读取：

- `OSINT_AGENT_HUB_URL`: 默认 `http://127.0.0.1:8088`
- `ADMIN_API_TOKEN`: 仅用于注册或重新注册 Agent
- `AGENT_API_TOKEN`: CLI 对非注册命令读取此环境变量；这里应存放当前 Agent 独立签发的 Token，而不是旧版全局共享值

以下命令从仓库根目录执行。先为当前 shell 设置模块搜索路径：

```bash
cd /path/to/osint-agent-network
export PYTHONPATH="$PWD/backend"
```

注册 Agent：

```bash
python3 -m app.agent_client register \
  --role-tier reader \
  --agent-name codex-desktop \
  --agent-type codex \
  --capability domain \
  --capability company \
  --capability theharvester \
  --capability amass
```

认领任务：

```bash
python3 -m app.agent_client claim \
  --agent-id <agent-id> \
  --capability domain
```

写入事件：

```bash
python3 -m app.agent_client event \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --level info \
  --message "开始执行 theHarvester" \
  --metadata '{"tool":"theharvester"}'
```

写入实体：

```bash
python3 -m app.agent_client entity \
  --task-id <task-id> \
  --type email \
  --value admin@example.com \
  --source-tool theharvester \
  --confidence 0.82
```

写入证据：

```bash
python3 -m app.agent_client evidence \
  --task-id <task-id> \
  --entity-value admin@example.com \
  --kind search_result \
  --source-tool theharvester \
  --snippet "公开搜索结果命中"
```

写入关系：

```bash
python3 -m app.agent_client relationship \
  --task-id <task-id> \
  --from example.com \
  --to admin@example.com \
  --type domain_has_email \
  --confidence 0.74
```

完成任务：

```bash
python3 -m app.agent_client complete \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --status COMPLETED \
  --summary "发现 1 条线索" \
  --report-file report.md \
  --confidence 0.91
```

## Local Tool Adapter Flow

CLI Agent 可以使用内置适配器运行本地 OSINT 工具，或解析已有 JSON artifact，并按标准协议自动写回实体、证据和关系。

Dry-run 解析 Sherlock 输出，不写回 API：

```bash
python3 -m app.agent_client run-tool \
  --tool sherlock \
  --target-type username \
  --target admin \
  --input-file data/jobs/sherlock_admin/output.json \
  --dry-run
```

运行本地 Sherlock 并写回任务中心：

```bash
python3 -m app.agent_client run-tool \
  --tool sherlock \
  --target-type username \
  --target admin \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --workdir data/jobs/<task-id>/sherlock_admin \
  --timeout 120
```

解析 theHarvester JSON 并写回任务中心：

```bash
python3 -m app.agent_client run-tool \
  --tool theharvester \
  --target-type domain \
  --target example.com \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --input-file data/jobs/<task-id>/theharvester_report.json
```

解析 Amass JSONL 并写回任务中心：

```bash
python3 -m app.agent_client run-tool \
  --tool amass \
  --target-type domain \
  --target example.com \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --input-file data/jobs/<task-id>/amass_example.com.jsonl
```

运行本地 Amass 被动枚举并写回任务中心：

```bash
python3 -m app.agent_client run-tool \
  --tool amass \
  --target-type domain \
  --target example.com \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --workdir data/jobs/<task-id>/amass_example.com \
  --timeout 1200
```

其他工具使用同一个 `run-tool` 入口：

```bash
python3 -m app.agent_client run-tool \
  --tool ghunt \
  --target-type email \
  --target target@gmail.com \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --workdir data/jobs/<task-id>/ghunt_target

python3 -m app.agent_client run-tool \
  --tool phoneinfoga \
  --target-type phone \
  --target +639171234567 \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --workdir data/jobs/<task-id>/phoneinfoga_target

python3 -m app.agent_client run-tool \
  --tool spiderfoot \
  --target-type domain \
  --target example.com \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --workdir data/jobs/<task-id>/spiderfoot_example.com

python3 -m app.agent_client run-tool \
  --tool reconng \
  --target-type domain \
  --target example.com \
  --task-id <task-id> \
  --agent-id <agent-id> \
  --workdir data/jobs/<task-id>/reconng_example.com
```

当前内置适配器输出规则：

- `sherlock`: 保留 `CLAIMED`/`FOUND`/`EXISTS` 命中的平台，写入 `username`、`profile_url`、`profile_exists`、`username_has_profile`。
- `theharvester`: 写入 `domain`、`email`、`username`、`subdomain`、`url`，并生成 `domain_exposes_email`、`email_has_username`、`domain_has_subdomain`、`domain_referenced_by_url`。
- `amass`: 解析 JSONL 行，写入 `domain`、`subdomain`、`ip`，并生成 `amass_name_discovery`、`dns_resolution`、`domain_has_subdomain`、`subdomain_resolves_to_ip`。
- `ghunt`: 写入 `email`、`real_name`、`profile_url`，并生成 `google_account_exists`、`negative_result`、`email_has_real_name`、`email_has_profile`。
- `phoneinfoga`: 写入 `phone`、`url`，并生成 `phone_metadata`、`phone_public_footprint`、`phone_referenced_by_url`。
- `spiderfoot`: 将高价值事件映射为 `email`、`subdomain`、`ip`、`url`、`username`、`real_name`、`company`，统一生成 `spiderfoot_event` 与 `target_has_finding`。
- `reconng`: 解析 JSON 报告中的 hosts、contacts、companies，生成 `reconng_report_record` 与 `reconng_finding`。
- `company_news`: 通过 GNews/Google News RSS 发现企业新闻，使用 Newspaper4k 解析正文，生成 `company_news_report`、`news_buying_signal`、`news_risk_signal`。

## Role-Based Company Job Output Standard

职责型 Agent 不一定直接调用单个底层工具，但必须写回同一套结构化协议。

### `enterprise_intel_agent`

Required outputs:

- `organization`: 企业名称。
- `domain` or `external_link`: 官网或公开主页。
- `phone` / `email`: 企业公开联系方式。
- `bio_snippet`: 主营业务、行业、地址或注册信息摘要。
- relationships: `company_has_website`, `company_has_phone`, `company_has_email`, `company_has_business_scope`.

### `social_intel_agent`

Required outputs:

- `profile_url`, `username`, `social_profile`, `platform_account`.
- `bio_snippet`, `declared_location`, `interest_tag` when public and relevant.
- relationships: `person_has_social_profile`, `company_has_social_profile`, `profile_mentions_company`.

### `contact_discovery_agent`

Required outputs:

- Separate company contact from personal/decision-maker contact.
- Use `person_has_contact` for decision-maker contact.
- Use `company_has_phone` / `company_has_email` for organization contact.
- If ownership is unclear, mark confidence lower and explain in evidence.

### `supply_chain_agent`

Required outputs:

- `organization` nodes for upstream, downstream, partner, distributor, retailer, or customer type.
- relationships: `company_has_partner`, `company_has_supplier`, `company_has_customer_type`.
- Evidence should explain why the relationship exists.

### `purchase_intent_agent`

Required outputs:

- `interest_tag` or `bio_snippet` describing purchase category and demand fit.
- relationships: `company_has_purchase_intent`.
- Report whether the signal is direct, inferred, or unconfirmed.

### `news_intel_agent`

Required outputs:

- `news_article`, `news_summary`, `published_at`, `external_link` for public company news.
- Evidence kinds: `company_news_report`, `news_business_event`, `news_buying_signal`, `news_risk_signal`.
- relationships: `company_has_news_article`, `news_supports_business_event`, `news_supports_buying_signal`, `news_supports_risk_signal`.
- News conclusions must include title, source media, publication date when available, URL, and the exact claim supported by the article.

### `cross_verification_agent`

Required outputs:

- Events documenting conflicts and source quality.
- Evidence showing source rank, Admiralty Code, and conflict resolution.
- Lower confidence for unsupported or contradictory entities.
- Disinformation/noise checks for same-name, repeated aggregator text, and unsupported claims.

### `analysis_judgement_agent`

Required outputs:

- Final summary and `report_markdown`.
- `confidence` for the mature profile.
- Graph-ready entities and relationships for the 23-slot template when missing fields can be derived from verified evidence.
- `PIR`: 3-5 priority questions and short answers.
- `BLUF`: first paragraph with the core judgement, confidence, and business implication.
- `ACH`: at least two competing hypotheses, with supporting and contradictory evidence.
- `I&W`: indicators, triggered indicators, target action, time window, and confidence.
- `directed_collection`: 2-5 next collection actions based on the remaining intelligence gaps.

Recommended report skeleton:

```markdown
# BLUF
核心判断：...
置信度：很有可能 / 有可能 / 可能性较低
So what：...

## PIR 回答
- PIR-1: ...

## 确认事实
| 事实 | Admiralty Code | 来源 | 证据 |

## ACH 竞争性假设
| 假设 | 一致证据 | 矛盾证据 | 状态 |

## I&W 征候矩阵
| 征候 | 状态 | 证据 | 影响 |

## 定向采集计划
- 下一步要查什么，为什么查。

## 行动建议
- 建议 1
```

Agents must not present active deception or counter-information operations as an automated system action. If such a tactic is discussed by a human operator, it belongs in manual strategy notes, not in executable jobs.

## Credential Configuration

工具凭证只从 Agent 运行环境读取，不写入任务中心、事件、证据或报告。推荐在 <production-host> 的服务启动脚本或 shell profile 中配置：

```bash
export OSINT_LLM_BASE_URL=http://192.0.2.10:6780/v1
export OSINT_LLM_API_KEY=<redacted>
export OSINT_LLM_MODEL=gpt-5.4
export SPIDERFOOT_BASE_URL=http://127.0.0.1:5001
export SPIDERFOOT_API_KEY=<redacted>
export PHONEINFOGA_BASE_URL=http://127.0.0.1:5000
export PHONEINFOGA_API_KEY=<redacted>
export GHUNT_COMMAND=ghunt
export GHUNT_COOKIE_PATH=/home/osint/.config/ghunt/cookies.txt
```

CLI 适配器会在命令摘要中隐藏 URL query 和凭证明文。GHunt Cookie 刷新仍由运维侧处理，适配器不会自动获取或刷新 Cookie。

检查情报官中转模型 API 配置：

```bash
python3 -m app.agent_client llm-check --no-call
```

实际连通性测试：

```bash
python3 -m app.agent_client llm-check
```

API 状态接口只返回脱敏后的 Key：

```http
GET /api/llm/status
```

## API-Key Relay Note

If an agent needs to call an external model or relay API, it should read that configuration from its own runtime environment. This task hub only stores OSINT task state and evidence. Do not write API keys into events, evidence snippets, or reports.
