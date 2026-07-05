# 企业与决策人图谱模板

Version: 0.2
Updated: 2026-05-20

本文定义网页端固定图谱的内容框架、证据关系和展示规则。后续任何企业背调任务都按这个模板填充，避免图谱随着数据增多变乱。

## 1. 布局结构

固定模板共有 23 个槽位：

- 顶部证据 5 个。
- 底部证据 5 个。
- 左侧决策人画像 5 个。
- 右侧企业信息 5 个。
- 中间核心内容 3 个。

```text
证据1        证据2        证据3        证据4        证据5

决策人姓名    采购意图/需求匹配    企业名称
身份/职位                         主营业务/行业
决策人电话/邮箱  核心线索          企业网址
社媒/公开主页                     企业电话/邮箱
性别/年龄/习惯  上下游/合作伙伴    活动地区/常驻地区

证据6        证据7        证据8        证据9        证据10
```

企业信息和决策人画像必须并列存在，因为决策人价值来自其与企业、采购角色和业务场景的关系。

## 2. 23 个槽位定义

| 区域 | 槽位 ID | 显示标题 | 主要实体类型 |
| --- | --- | --- | --- |
| Top Evidence | `evidence_top_1` - `evidence_top_5` | 证据 | `evidence` |
| Decision | `decision_name` | 决策人姓名 | `identity` |
| Decision | `decision_role` | 身份/职位 | `bio_snippet` |
| Decision | `decision_contact` | 决策人电话/邮箱 | `email`, `phone` |
| Decision | `social_profile` | 社媒/公开主页 | `username`, `profile_url`, `social_profile`, `platform_account` |
| Decision | `personal_habit` | 性别/年龄/习惯 | `gender_claim`, `age_range`, `dietary_preference`, `hospitality_preference` |
| Core | `purchase_intent` | 采购意图/需求匹配 | `bio_snippet`, `interest_tag`, `public_personal_attribute` |
| Core | `core_clue` | 核心线索 | `seed` |
| Core | `upstream_downstream` | 上下游/合作伙伴 | `organization` |
| Company | `company_name` | 企业名称 | `organization` |
| Company | `business_scope` | 主营业务/行业 | `bio_snippet` |
| Company | `company_website` | 企业网址 | `domain`, `profile_url`, `external_link` |
| Company | `company_contact` | 企业电话/邮箱 | `phone`, `email` |
| Company | `activity_region` | 活动地区/常驻地区 | `declared_location`, `likely_activity_region` |
| Bottom Evidence | `evidence_bottom_1` - `evidence_bottom_5` | 证据 | `evidence` |

如果某个槽位暂时没有数据，显示 `待补充`，但槽位仍然保留。

## 3. 主面板与折叠区

主面板只显示最重要的一条或少量内容：

- 优先显示置信度高的实体。
- 优先显示有证据支持的实体。
- 优先显示 A/B 级来源。
- 优先显示与核心线索、企业、决策人有关系边的数据。

多余信息进入折叠区或详情面板，不直接堆在图谱上。图谱负责展示主线，详情负责承载丰富数据。

## 4. 证据连线标准

每条结论都应能沿着线找到来源：

```text
来源工具/网站 -> 证据片段 -> 实体/结论 -> 关系对象
```

常用边类型：

| 边类型 | 中文标签 | 含义 |
| --- | --- | --- |
| `source_emitted_entity` | 信息来源 | 某来源直接产生一个实体 |
| `source_emitted_evidence` | 信息来源 | 某来源产生一条证据 |
| `supports_entity` | 证据支持 | 证据支持某实体 |
| `supports_relationship` | 关系来源 | 来源支持某条关系 |
| `company_has_phone` | 企业电话 | 电话属于企业 |
| `company_has_email` | 企业邮箱 | 邮箱属于企业 |
| `person_has_contact` | 个人联系方式 | 联系方式属于决策人 |
| `person_represents_company` | 任职/代表 | 决策人与企业的职位关系 |
| `company_has_website` | 企业网站 | 官网或主页关系 |
| `company_has_business_scope` | 主营业务 | 企业与业务描述关系 |
| `company_has_partner` | 合作伙伴 | 企业与伙伴/上下游关系 |
| `company_has_purchase_intent` | 采购意图 | 企业与采购需求关系 |

## 5. 视觉规则

沿用 `DESIGN.md` 的轻量工作台风格：

- 背景使用浅色。
- 不使用深色大面积面板。
- 不使用粗线。
- 所有图谱线条统一为极细彩线，视觉上接近末端细点。
- 不用线宽表达置信度，避免页面显乱。
- 不同板块用浅色区分，线条颜色跟随板块语义。
- 证据和实体都可点击查看完整来源、片段和写回 Agent。

## 6. 信息填充标准

### 企业侧

必须优先填：

- 企业名称。
- 企业网址。
- 企业电话。
- 企业邮箱。
- 主营业务/行业。
- 活动地区/常驻地区。
- 上游、下游、合作伙伴或客户类型。

### 决策人侧

必须优先填：

- 决策人姓名。
- 身份/职位。
- 公开邮箱。
- 公开电话。
- 社媒/公开主页。
- 公开性别线索。
- 公开年龄区间线索。
- 商务习惯、公开兴趣、饮食偏好或接待偏好线索。

### 中间核心

必须优先填：

- 初始核心线索。
- 采购意图或需求匹配。
- 企业上下游/合作伙伴。

## 7. 不确定信息处理

- 无来源：不进主图谱。
- 单一弱来源：可进折叠区，标注待复核。
- 来源冲突：显示冲突状态，等待人工确认。
- 涉及私人生活但无明确商务价值：不放主图谱。

## 8. 验收清单

- 页面打开后图谱不为空。
- 固定槽位完整存在。
- 企业和决策人并列展示。
- 顶部 5 个证据、底部 5 个证据存在。
- 中间有核心线索、采购意图、上下游/合作伙伴。
- 所有线条统一很细。
- 结论能追溯来源。
- 多余数据被折叠，而不是挤满画布。
