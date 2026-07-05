# 海关数据供应链分析功能

**版本**: 1.1  
**更新日期**: 2026-07-02

---

## 功能概述

基于已集成的跨境魔方海关API，通过反向查询实现零额外成本的供应链情报采集：

- ✅ **下游客户识别**: 查询供应商的所有进口商/买家
- ✅ **上游供应商识别**: 查询买家的所有供应商/出口商
- ✅ **贸易关系量化**: 统计交易次数、产品类别、时间范围
- ✅ **Web可视化**: 一键查询，图形化展示供应链网络
- ✅ **深度调查联动**: 点击伙伴名称即可创建新的调查任务

---

## 使用方法

### 1. Web界面操作

1. 创建公司类型的调查任务（`seed_type=company`）
2. 在调查详情页面，找到**"海关供应链分析"**面板
3. 点击**"分析供应链"**按钮
4. 等待查询完成（通常5-15秒）
5. 查看结果：
   - **下游客户**标签：显示所有进口该公司产品的买家
   - **上游供应商**标签：显示该公司所有的供应商
6. 点击任何伙伴公司的**"深度调查"**按钮，创建后续任务

### 2. API调用

**端点**: `POST /api/customs/supply-chain`

**请求头**:
```http
Authorization: Bearer <ADMIN_API_TOKEN>
Content-Type: application/json
```

**请求体**:
```json
{
  "company": "SHANDONG ORIENT ALUMINIUM CO., LTD."
}
```

**响应示例**:
```json
{
  "company": "SHANDONG ORIENT ALUMINIUM CO., LTD.",
  "downstream": {
    "customers": [
      {
        "name": "FAMILY HOSPITALITY LLC",
        "country": "US",
        "trade_count": 15,
        "products": ["ALUMINUM PROFILES", "METAL PARTS"],
        "first_trade": "2023-05-10",
        "last_trade": "2024-11-20"
      }
    ],
    "total_count": 28
  },
  "upstream": {
    "suppliers": [
      {
        "name": "ALUMINUM ORE SUPPLIER CO",
        "country": "CN",
        "trade_count": 42,
        "products": ["ALUMINUM INGOT", "RAW MATERIALS"],
        "first_trade": "2022-01-15",
        "last_trade": "2024-12-01"
      }
    ],
    "total_count": 12
  }
}
```

**错误语义**:

| 状态码 | 含义 | 维护判断 |
|-------|------|----------|
| 200 | 查询完成 | `total_count=0` 才表示真实无结果 |
| 401 | 管理授权失败 | 检查 `ADMIN_API_TOKEN` / `VITE_ADMIN_API_TOKEN` |
| 503 | 海关 API 未配置 | 检查后端 `UPKUAJING_AUTHORIZATION` |
| 502 | 上游海关 API 错误或不可达 | 检查第三方服务和网络 |
| 504 | 上游请求超时 | 检查第三方服务响应时间和超时设置 |

非 2xx 响应不是“未找到供应链”，前端会显示错误提示。

### 3. 命令行工具

使用现有的agent_client（待集成）:

```bash
cd /Users/aidi/情报官/osint-agent-network

PYTHONPATH=backend python3 -c "
from app.tools.customs_supply_chain import CustomsSupplyChainAdapter

adapter = CustomsSupplyChainAdapter()
result = adapter.analyze_full_supply_chain('SHANDONG ORIENT ALUMINIUM CO., LTD.')

print(f'实体数量: {len(result.entities)}')
print(f'关系数量: {len(result.relationships)}')
"
```

---

## 数据来源与可信度

### 数据来源
- **跨境魔方海关API** (`UPKUAJING_AUTHORIZATION`)
- 数据覆盖：全球主要国家海关提单数据
- 更新频率：1-3个月延迟

### 置信度计算

系统根据交易频次自动计算关系置信度：

| 交易次数 | 置信度 | 说明 |
|---------|-------|------|
| 1次 | 0.70 | 可能是试订单或一次性交易 |
| 2-5次 | 0.80 | 稳定的贸易关系 |
| 6-10次 | 0.85 | 长期合作伙伴 |
| 11+次 | 0.90 | 核心供应链伙伴 |

---

## 覆盖范围

### ✅ 能查到的场景

1. **B2B制造业** - 主要适用场景
   - 铝型材、金属制品
   - 机械设备、电子产品
   - 化工原料、纺织品
   - 家具、建材

2. **跨境电商**
   - 有自主品牌的卖家
   - 大型供应商

3. **贸易公司**
   - 进出口代理
   - 批发商

### ⚠️ 查不到的场景

1. **纯内贸企业** - 无进出口记录
2. **服务业公司** - 软件、咨询、金融
3. **零售终端** - 不直接参与国际贸易
4. **小型个体户** - 贸易量低于海关记录阈值

**覆盖率估算**: 
- B2B制造业: **70-80%**
- 跨境电商: **50-60%**
- 其他行业: **20-30%**

---

## 技术架构

### 后端组件

```
CustomsSupplyChainAdapter (工具适配器)
    ↓
UpkuajingCustomsClient (海关API客户端)
    ↓
POST /customs/trade/list (第三方API)
    ↓
解析 & 聚合
    ↓
生成 entities, evidence, relationships
```

### 关键文件

- `backend/app/tools/customs_supply_chain.py` - 核心适配器
- `backend/app/main.py:240-292` - API接口
- `frontend/src/components/SupplyChainPanel.tsx` - 前端面板
- `frontend/src/styles.css:2950-3179` - 样式定义
- `docs/MAINTENANCE_RELIABILITY_2026-07-02.md` - 错误语义和维护检查

---

## 配置要求

### 必需配置

在 `.env` 文件中设置：

```bash
# 跨境魔方海关API授权
UPKUAJING_AUTHORIZATION="Bearer your_token_here"

# 可选：跨境魔方API地址（默认为官方地址）
UPKUAJING_BASE_URL=https://saas.upkuajing.com

# 可选：超时设置（秒）
UPKUAJING_TIMEOUT_SECONDS=30
```

### 权限要求

供应链查询接口需要管理员权限：
- 需要 `ADMIN_API_TOKEN` 或 `AGENT_API_TOKEN`
- 前端需要配置 `VITE_ADMIN_API_TOKEN`

---

## 常见问题

### Q1: 为什么查询不到任何结果？

**可能原因**:
1. 该公司没有进出口业务（纯内贸）
2. 公司名称不准确（尝试官方英文全称）
3. 海关数据更新延迟（最近2-3个月的数据可能未录入）
4. 跨境魔方API授权过期

**解决方法**:
```bash
# 检查API配置
curl -sS http://127.0.0.1:8088/api/customs/trade/list \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"seller": "测试公司名"}'

# 如果返回401: Token未配置或错误
# 如果返回502: 跨境魔方API连接失败
# 如果返回200但list为空: 该公司确实无数据
```

### Q2: 查询速度慢怎么办？

当前查询需要调用2次API（上游+下游），平均耗时10-20秒。

**优化方案**（待实施）:
- [ ] 添加Redis缓存（24小时有效期）
- [ ] 后台异步查询
- [ ] 增量更新机制

### Q3: 如何批量查询多个公司？

**方案1**: 使用脚本循环

```python
companies = [
    "SHANDONG ORIENT ALUMINIUM CO., LTD.",
    "ANOTHER COMPANY INC.",
]

for company in companies:
    adapter = CustomsSupplyChainAdapter()
    result = adapter.analyze_full_supply_chain(company)
    # 处理结果...
```

**方案2**: 创建多个调查任务，逐个点击查询

### Q4: 能否自动触发供应链查询？

**当前**: 需要手动点击"分析供应链"按钮

**未来增强** (需要开发):
- [ ] 在公司调查创建时自动查询
- [ ] 定时刷新机制
- [ ] 自动将主要客户/供应商创建为子任务

---

## 数据隐私与合规

### 数据来源合法性
- 海关提单是**公开数据**
- 跨境魔方已获得合法授权
- 仅用于商业背调和市场研究

### 使用限制
- ✅ 允许：商业尽职调查、市场分析、竞争情报
- ❌ 禁止：恶意竞争、数据转售、侵犯商业机密

### 数据保留
- 查询结果存储在本地SQLite数据库
- 建议定期清理历史数据（`backup.sh`自动备份）

---

## 未来增强计划

### 短期 (1-2个月)

- [ ] 添加缓存机制（避免重复查询）
- [ ] 批量查询接口
- [ ] 导出Excel/PDF报告
- [ ] 供应链关系图谱可视化（3D/力导向图）

### 中期 (3-6个月)

- [ ] 集成更多数据源（ImportYeti、企查查）
- [ ] 供应链风险评估（集中度、地缘风险）
- [ ] 竞争对手供应链对比
- [ ] 历史趋势分析

### 长期 (6-12个月)

- [ ] AI辅助供应链优化建议
- [ ] 供应链中断预警
- [ ] 行业供应链地图

---

## 技术支持

### 日志查看

```bash
# 查看后端日志
tail -f /Users/aidi/情报官/osint-agent-network/data/api.log

# 查看浏览器控制台
# Chrome DevTools -> Console
```

### 测试接口

```bash
# 健康检查
curl http://127.0.0.1:8088/api/health

# 测试供应链查询
curl -X POST http://127.0.0.1:8088/api/customs/supply-chain \
  -H "Authorization: Bearer $ADMIN_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"company": "TEST COMPANY"}'
```

### 运行测试

```bash
cd /Users/aidi/情报官/osint-agent-network
PYTHONPATH=backend python3 -m unittest backend.tests.test_customs_supply_chain
```

---

## 更新日志

### v1.0 (2026-06-30)
- ✅ 初始版本发布
- ✅ 支持下游客户查询
- ✅ 支持上游供应商查询
- ✅ Web界面集成
- ✅ 单元测试覆盖

---

**文档维护**: 本文档应与代码同步更新  
**反馈渠道**: 项目Issue或内部技术群
