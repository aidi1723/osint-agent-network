# 情报官 OSINT Agent Network - 项目结尾、维护与部署日志

**项目名称**: 情报官 OSINT Agent Network
**项目目录**: `/opt/osint-agent-network` (<production-host>) / `/path/to/osint-agent-network` (本地)
**最后更新**: 2026-07-02
**项目状态**: 生产就绪 ✅

---

## 一、项目结尾日志（Project Closure Log）

### 1.1 项目完成概述

本项目在 2026 年 5-6 月期间经历了从安全审计到功能增强的完整闭环。以下是关键里程碑：

#### 初始阶段（2026-05-19 至 2026-05-24）
- 项目初始化、架构搭建
- 多 Agent 编排系统实现
- 23 位图谱模板设计
- <production-host> 部署与 systemd 配置
- Intelligence Maturity Gate 实现
- 证据账本、事实晋级、交叉验证矩阵

#### 增强阶段（2026-06-30）
- **Zero-Cost Intelligence Aggregation** 实施
- 海关供应链分析功能
- 联系方式/社交媒体/产品智能聚合
- <production-host> 生产部署与验证

#### 可靠性部署阶段（2026-07-02）
- 修复海关供应链错误语义，避免把凭证/上游失败显示为无数据。
- 修复产品情报与社媒情报聚合契约，补齐回归测试。
- 修复前端错误状态和 CSS 构建警告。
- 修复 `production_readiness.py` 对受保护读接口的授权请求。
- 重新部署到 <production-host>，启用 user-level systemd 服务，并验证 `ready: true`。

### 1.2 最终项目状态

#### 核心功能矩阵

| 功能模块 | 状态 | 成熟度 | 说明 |
|---------|------|--------|------|
| 多 Agent 编排 | ✅ 生产 | 高 | 7 种职责型 Agent 已实现 |
| 工具适配器 | ✅ 生产 | 高 | 10+ 种 OSINT 工具 |
| 证据闭环 | ✅ 生产 | 高 | Entity → Evidence → Fact → Report |
| 图谱展示 | ✅ 生产 | 高 | 23 位固定图谱模板 |
| 情报聚合 | ✅ 生产 | 中 | 联系方式/社媒/产品自动聚合 |
| 供应链分析 | ✅ 生产 | 中 | 跨境魔方 API 集成 |
| IntelCore 预测 | ✅ 生产 | 中 | PIR/ACH/I&W/BLUF |
| 空白 Lead 补全 | ✅ 生产 | 高 | Sparse Lead 逆向补全 |
| 前端看板 | ✅ 生产 | 高 | React + TypeScript + Vite |
| API Hub | ✅ 生产 | 高 | Python http.server + SQLite |

#### 代码统计

```
后端代码:     ~8,500 行 (Python)
前端代码:     ~6,000 行 (TypeScript/React)
样式代码:     ~3,600 行 (CSS)
测试代码:     ~1,500 行 (Python/TypeScript)
文档:        ~6,000 行 (Markdown)
配置文件:     ~500 行 (YAML/JSON/Shell)

总计:        ~26,000 行
```

#### 关键文件清单

```
根目录:
├── README.md                           # 项目主文档
├── DESIGN.md                           # UI 设计规范
├── EULA.md                             # 最终用户许可协议
├── LICENSE                             # 商业许可
├── docker-compose.yml                  # Docker Compose 配置
├── .env.example                        # 环境变量模板
├── agent-manifest.json                 # Agent/Skill 治理定义
│
├── backend/
│   ├── app/
│   │   ├── main.py                     # API 入口 (主要路由)
│   │   ├── store.py                    # SQLite Store
│   │   ├── worker.py                   # Worker 调度器
│   │   ├── agent_client.py             # Agent CLI 客户端
│   │   ├── core/
│   │   │   ├── registry.py             # 工具注册表
│   │   │   ├── contact_discovery.py    # 联系方式聚合 (NEW)
│   │   │   ├── social_intelligence.py  # 社媒情报聚合 (NEW)
│   │   │   ├── product_intelligence.py # 产品情报聚合 (NEW)
│   │   │   ├── intel_core_v3.py        # IntelCore 引擎
│   │   │   ├── evidence_graph.py       # 证据图谱
│   │   │   ├── quality_gate.py         # 质量闸门
│   │   │   └── ...
│   │   └── tools/
│   │       ├── customs_supply_chain.py # 海关供应链 (NEW)
│   │       └── ...
│   └── tests/
│       ├── test_core.py
│       ├── test_agent_protocol.py
│       ├── test_worker.py
│       ├── test_graph.py
│       └── test_customs_supply_chain.py # (NEW)
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx                    # 主入口
│   │   ├── styles.css                  # 全局样式
│   │   ├── types.ts                    # TypeScript 类型
│   │   └── components/
│   │       ├── InvestigationDetail.tsx # 调查详情
│   │       ├── GraphView.tsx           # 图谱视图
│   │       ├── IntelligencePanel.tsx   # 情报汇总面板 (NEW)
│   │       ├── SupplyChainPanel.tsx    # 供应链分析面板 (NEW)
│   │       └── ...
│   └── .env.production                 # 生产环境配置
│
├── agents/                             # Agent 角色定义
├── skills/                             # Skill 工作流定义
├── scripts/
│   ├── start.sh                        # 启动脚本
│   ├── stop.sh                         # 停止脚本
│   ├── status.sh                       # 状态检查
│   ├── backup.sh                       # 备份脚本
│   ├── healthcheck.sh                  # 健康检查
│   ├── verify.sh                       # 项目验证
│   ├── check_agents.py                 # Agent 治理检查
│   ├── regression_smoke.py             # 回归烟测
│   ├── production_readiness.py         # 生产就绪检查
│   └── upkuajing_trade_list.py         # 跨境魔方 CLI 工具
│
├── docs/
│   ├── UPDATE_LOG.md                   # 更新日志
│   ├── AGENT_PROTOCOL.md               # Agent 协议
│   ├── CUSTOMS_SUPPLY_CHAIN.md         # 供应链功能文档
│   ├── INTELLIGENCE_AGGREGATION.md     # 情报聚合文档
│   ├── N100_DEPLOYMENT_RUNBOOK.md      # <production-host> 部署 Runbook
│   ├── REAL_OSINT_WORKFLOW.md          # 真实 OSINT 工作流
│   └── ...
│
├── data/
│   └── osint.sqlite                    # SQLite 数据库
│
└── reports/                            # 报告输出目录
```

### 1.3 技术债务与遗留问题

#### 已知问题

| 问题 | 严重性 | 状态 | 说明 |
|------|--------|------|------|
| CSS 语法警告 | 低 | 已解决 | 2026-07-02 已清理末尾多余大括号 |
| UPKUAJING 未配置 | 中 | 可选 | 供应链分析需要第三方凭证；非 2xx 不再当作无数据 |
| 无用户认证系统 | 中 | 待实现 | 当前只有 Token 保护 |
| 无审计日志 | 中 | 待实现 | 操作记录追踪 |
| 无 HTTPS | 高 | 待解决 | 需要配置反向代理或证书 |

#### 后续增强建议

**短期优先级（1-2 个月）**:
1. ⬜ 邮箱有效性验证（SMTP 检查）
2. ⬜ 电话号码格式统一
3. ⬜ 社交媒体活跃度评分
4. ⬜ 情报聚合缓存（24 小时 TTL）
5. ✅ CSS 警告修复（2026-07-02）

**中期优先级（3-6 个月）**:
6. ⬜ AI 辅助产品分类
7. ⬜ 联系人角色识别（CEO、采购、销售）
8. ⬜ 社交关系图谱
9. ⬜ 审计日志系统
10. ⬜ PDF/HTML 报告导出模板

**长期优先级（6 个月以上）**:
11. ⬜ 用户认证与权限分层
12. ⬜ 集成专业数据源（Hunter.io、Clearbit）
13. ⬜ 实时社交媒体监控
14. ⬜ 产品市场趋势分析
15. ⬜ HTTPS 部署

---

## 二、维护日志（Maintenance Log）

### 2.1 日常维护检查清单

#### 每日检查（5 分钟）
```bash
#!/bin/bash
# 保存为: scripts/daily_check.sh
# 建议通过 cron 每天 9:00 自动执行

echo "=== 情报官每日健康检查 $(date) ==="

# 1. 服务状态
echo "1. 服务状态:"
systemctl --user is-active osint-agent-network-api.service
systemctl --user is-active osint-agent-network-web.service

# 2. API 健康检查
echo "2. API 健康:"
curl -sS http://127.0.0.1:8088/api/health

# 3. Web UI 可访问性
echo "3. Web UI:"
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://127.0.0.1:3008/

# 4. 数据库大小
echo "4. 数据库大小:"
ls -lh /opt/osint-agent-network/data/osint.sqlite

# 5. 磁盘空间
echo "5. 磁盘空间:"
df -h /opt/osint-agent-network/

# 6. 最近错误日志
echo "6. 最近错误 (过去 5 分钟):"
journalctl --user -u osint-agent-network-api.service --since "5 min ago" -p err
```

#### 每周检查（15 分钟）

```bash
#!/bin/bash
# 保存为: scripts/weekly_check.sh

echo "=== 情报官每周健康检查 $(date) ==="

# 1. 数据库完整性
echo "1. 数据库完整性:"
cd /opt/osint-agent-network
python3 -c "
import sqlite3
conn = sqlite3.connect('data/osint.sqlite')
# 检查表是否存在
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print(f'  表数量: {len(tables)}')
for t in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM {t[0]}').fetchone()[0]
    print(f'  - {t[0]}: {count} 行')
conn.close()
"

# 2. 备份状态
echo "2. 备份状态:"
ls -lht /var/backups/osint-agent-network/ | head -6

# 3. 磁盘使用趋势
echo "3. 磁盘使用:"
df -h /home/osint/

# 4. 内存使用
echo "4. 内存:"
free -h

# 5. 服务运行时间
echo "5. 服务运行时间:"
ps -p $(systemctl --user show -p MainPID osint-agent-network-api.service | cut -d= -f2) -o etime=
ps -p $(systemctl --user show -p MainPID osint-agent-network-web.service | cut -d= -f2) -o etime=

# 6. 备份保留清理
echo "6. 清理旧备份 (保留最近 14 份):"
cd /var/backups/osint-agent-network/
ls -t backup-* | tail -n +15 | xargs -r rm -f
echo "  完成"
```

#### 每月检查（30 分钟）

```bash
#!/bin/bash
# 保存为: scripts/monthly_check.sh

echo "=== 情报官月度维护检查 $(date) ==="

# 1. 运行完整测试套件
echo "1. 运行后端测试:"
cd /opt/osint-agent-network
PYTHONPATH=backend python3 -m unittest backend.tests.test_core backend.tests.test_agent_protocol backend.tests.test_worker backend.tests.test_graph backend.tests.test_customs_supply_chain

# 2. 运行回归烟测
echo "2. 回归烟测:"
python3 scripts/regression_smoke.py

# 3. 运行生产就绪检查
echo "3. 生产就绪检查:"
python3 scripts/production_readiness.py

# 4. Agent 治理验证
echo "4. Agent 治理检查:"
python3 scripts/check_agents.py

# 5. 数据库优化
echo "5. 数据库优化:"
python3 -c "
import sqlite3
conn = sqlite3.connect('data/osint.sqlite')
conn.execute('PRAGMA optimize')
conn.execute('PRAGMA integrity_check')
result = conn.execute('PRAGMA integrity_check').fetchone()
print(f'  数据库完整性: {result[0]}')
conn.execute('VACUUM')
conn.execute('REINDEX')
conn.close()
print('  优化完成')
"

# 6. 日志轮转检查
echo "6. Systemd 日志大小:"
journalctl --user -u osint-agent-network-api.service --disk-usage
journalctl --user -u osint-agent-network-web.service --disk-usage

# 7. 清理调查垃圾数据
echo "7. 调查统计:"
python3 -c "
import sqlite3
conn = sqlite3.connect('data/osint.sqlite')
total = conn.execute('SELECT COUNT(*) FROM investigations').fetchone()[0]
active = conn.execute(\"SELECT COUNT(*) FROM investigations WHERE status IN ('CREATED','CLAIMED','RUNNING')\").fetchone()[0]
failed = conn.execute(\"SELECT COUNT(*) FROM investigations WHERE status='FAILED'\").fetchone()[0]
completed = conn.execute(\"SELECT COUNT(*) FROM investigations WHERE status='COMPLETED'\").fetchone()[0]
print(f'  总调查: {total}, 活跃: {active}, 完成: {completed}, 失败: {failed}')
conn.close()
"
```

### 2.2 最近部署记录：2026-07-02 可靠性升级

**目标主机**: `<production-host>`
**目标路径**: `/opt/osint-agent-network`
**访问地址**: `http://192.0.2.10:3008/`
**API 地址**: `http://192.0.2.10:8088/api/health`
**部署日志**: `docs/N100_DEPLOYMENT_LOG_2026-07-02.md`

#### 部署结果

```text
服务模式: user-level systemd
API 服务: osint-agent-network-api.service active/enabled
Web 服务: osint-agent-network-web.service active/enabled
监听端口: 0.0.0.0:8088, 0.0.0.0:3008
生产就绪: ready=true
```

#### 备份

```text
/var/backups/osint-agent-network/predeploy-20260702-163837.tar.gz
```

#### 验证结果

```text
bash scripts/verify.sh:
  Ran 110 tests ... OK
  Regression smoke: case_count=4, failed=0
  Frontend checks: passed
  Vite build: passed

python3 scripts/production_readiness.py:
  ready=true
  api/database/web/backup/tool health: ok
  tool_attention=7
```

#### 下次升级标准流程

```bash
# 1. 本地验证
cd /path/to/osint-agent-network
bash scripts/verify.sh

# 2. 远端备份
ssh <production-host> 'mkdir -p /var/backups/osint-agent-network && cd /home/osint/apps && tar \
  --exclude=osint-agent-network/frontend/node_modules \
  --exclude=osint-agent-network/frontend/dist \
  --exclude=osint-agent-network/data/jobs \
  --exclude=osint-agent-network/data/artifacts \
  --exclude=osint-agent-network/data/*.sqlite \
  --exclude=osint-agent-network/reports \
  -czf /var/backups/osint-agent-network/predeploy-$(date +%Y%m%d-%H%M%S).tar.gz \
  osint-agent-network'

# 3. 安全同步，保留远端 .env、数据库、任务产物和报告
rsync -az \
  --exclude '.env' \
  --exclude 'frontend/.env.production' \
  --exclude 'frontend/node_modules/' \
  --exclude 'frontend/dist/' \
  --exclude 'frontend/.vite/' \
  --exclude 'frontend.zip' \
  --exclude 'data/*.sqlite' \
  --exclude 'data/*.sqlite-*' \
  --exclude 'data/*.log' \
  --exclude 'data/*.pid' \
  --exclude 'data/jobs/' \
  --exclude 'data/artifacts/' \
  --exclude 'reports/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  ./ <production-host>:/opt/osint-agent-network/

# 4. 远端构建和验证
ssh <production-host> 'cd /opt/osint-agent-network/frontend && npm install && npm run build'
ssh <production-host> 'cd /opt/osint-agent-network && bash scripts/verify.sh'

# 5. 重启和验收
ssh <production-host> 'systemctl --user restart osint-agent-network-api.service osint-agent-network-web.service'
ssh <production-host> 'cd /opt/osint-agent-network && python3 scripts/production_readiness.py'
```

#### 注意事项

- `production_readiness.py` 需要读取 `.env` 并给 `/api/system/status` 带读 token；2026-07-02 已修复并增加测试。
- `tool_attention` 对按需 OSINT 工具是信息项，不阻塞平台运行。
- `npm install` 当前提示 4 个依赖审计项（2 low, 2 high），未阻塞部署；升级依赖要单独评估。
- 不要用 rsync 覆盖远端 `.env`、`frontend/.env.production`、`data/` 和 `reports/`。

### 2.3 备份策略

#### 自动化备份（Crontab）
```bash
# 添加 crontab
systemctl --user enable osint-agent-network-api.service osint-agent-network-web.service
# systemd 用户服务在登录时启动，无需 crontab

# 注册定时备份（使用 systemd timer）
# 创建: ~/.config/systemd/user/osint-agent-network-backup.service
cat > ~/.config/systemd/user/osint-agent-network-backup.service << 'EOF'
[Unit]
Description=OSINT Agent Network Backup

[Service]
Type=oneshot
ExecStart=/opt/osint-agent-network/scripts/backup.sh
StandardOutput=journal
EOF

# 创建: ~/.config/systemd/user/osint-agent-network-backup.timer
cat > ~/.config/systemd/user/osint-agent-network-backup.timer << 'EOF'
[Unit]
Description=Daily OSINT Agent Network Backup

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

# 启用 timer
systemctl --user daemon-reload
systemctl --user enable osint-agent-network-backup.timer
systemctl --user start osint-agent-network-backup.timer
```

#### 备份内容
```
备份位置: /var/backups/osint-agent-network/
备份频率: 每日 00:00
保留份数: 14 份（通过 BACKUP_KEEP_LAST 调整）
备份内容:
  - data/           # SQLite 数据库
  - reports/        # 报告输出
  - .env            # 环境变量快照
  - agents/         # Agent 角色定义
  - skills/         # Skill 工作流
```

#### 手动备份
```bash
# 立即执行备份
cd /opt/osint-agent-network
bash scripts/backup.sh

# 自定义保留份数
BACKUP_KEEP_LAST=30 bash scripts/backup.sh
```

### 2.3 监控指标

#### 关键指标

| 指标 | 阈值 | 检查方法 |
|------|------|---------|
| API 可用性 | 99.9% | `curl http://127.0.0.1:8088/api/health` |
| Web 可用性 | 99.9% | `curl http://127.0.0.1:3008/` |
| 数据库大小 | <500MB | `ls -lh data/osint.sqlite` |
| 磁盘可用 | >1GB | `df -h /home/osint/` |
| 内存使用 | <500MB | `free -h` |
| 调查失败率 | <10% | SQL 查询 FAILED 调查占比 |
| 备份延迟 | <24h | 检查备份时间戳 |

#### 告警脚本
```bash
#!/bin/bash
# 保存为: scripts/alert_check.sh
# 当异常时输出告警信息

API=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8088/api/health)
if [ "$API" != "200" ]; then
    echo "CRITICAL: API 不可用 (HTTP $API)"
fi

WEB=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:3008/)
if [ "$WEB" != "200" ]; then
    echo "CRITICAL: Web UI 不可用 (HTTP $WEB)"
fi

DB_SIZE=$(stat -f%z data/osint.sqlite 2>/dev/null || stat -c%s data/osint.sqlite)
if [ "$DB_SIZE" -gt 500000000 ]; then
    echo "WARNING: 数据库超过 500MB ($((DB_SIZE / 1024 / 1024))MB)"
fi

DISK_AVAIL=$(df -k . | tail -1 | awk '{print $4}')
if [ "$DISK_AVAIL" -lt 1048576 ]; then
    echo "CRITICAL: 磁盘可用 < 1GB"
fi

# 检查备份是否在 24 小时内
LATEST_BACKUP=$(ls -t /var/backups/osint-agent-network/backup-* 2>/dev/null | head -1)
if [ -n "$LATEST_BACKUP" ]; then
    BACKUP_AGE=$(($(date +%s) - $(stat -f%m "$LATEST_BACKUP" 2>/dev/null || stat -c%Y "$LATEST_BACKUP")))
    if [ "$BACKUP_AGE" -gt 86400 ]; then
        echo "WARNING: 最后一个备份超过 24 小时 ($((BACKUP_AGE / 3600))小时"
    fi
else
    echo "WARNING: 没有找到备份"
fi
```

### 2.4 数据库维护

#### 数据库优化
```bash
# 每月执行一次
cd /opt/osint-agent-network
python3 -c "
import sqlite3
conn = sqlite3.connect('data/osint.sqlite')

# 分析查询模式
conn.execute('PRAGMA analysis_limit=1000')
conn.execute('PRAGMA optimize')

# 检查完整性
result = conn.execute('PRAGMA integrity_check').fetchone()
print(f'Integrity: {result[0]}')

# 查看表统计
cursor = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
for row in cursor:
    count = conn.execute(f'SELECT COUNT(*) FROM \"{row[0]}\"').fetchone()[0]
    print(f'  {row[0]}: {count} rows')

# 清理空间
conn.execute('VACUUM')
conn.close()
print('Database optimized.')
"
```

#### 数据库备份（单独）
```bash
# 只备份数据库
cd /opt/osint-agent-network
cp data/osint.sqlite "/var/backups/osint-agent-network/osint-$(date +%Y%m%d-%H%M%S).sqlite"
```

### 2.5 服务管理

#### 启动
```bash
# 方法 1: 使用项目脚本
cd /opt/osint-agent-network
bash scripts/start.sh

# 方法 2: 使用 systemd
systemctl --user start osint-agent-network-api.service
systemctl --user start osint-agent-network-web.service
```

#### 停止
```bash
# 方法 1: 使用项目脚本
bash scripts/stop.sh

# 方法 2: 使用 systemd
systemctl --user stop osint-agent-network-api.service
systemctl --user stop osint-agent-network-web.service
```

#### 重启
```bash
systemctl --user restart osint-agent-network-api.service
systemctl --user restart osint-agent-network-web.service
```

#### 查看日志
```bash
# 实时日志
journalctl --user -u osint-agent-network-api.service -f
journalctl --user -u osint-agent-network-web.service -f

# 最近 100 行
journalctl --user -u osint-agent-network-api.service -n 100

# 今天的日志
journalctl --user -u osint-agent-network-api.service --since today

# 错误日志
journalctl --user -u osint-agent-network-api.service -p err
```

### 2.6 前端部署

```bash
# 开发模式（本地）
cd /path/to/osint-agent-network/frontend
npm run dev

# 生产构建 + 部署（<production-host>）
cd /opt/osint-agent-network/frontend
npm run build                # 构建到 dist/
systemctl --user restart osint-agent-network-web.service  # 重启 Web 服务
```

---

## 三、部署日志（Deployment Log）

### 3.1 部署历史

#### 部署 #1: 初始部署
- **日期**: 2026-05-21
- **目标**: <production-host> 初始安装
- **内容**: 项目基础架构、API Hub、Worker、Agent 协议
- **结果**: 成功

#### 部署 #2: 成熟度闸门
- **日期**: 2026-05-24
- **目标**: Intelligence Maturity Gate
- **内容**: 证据账本、事实晋级、ACH/I&W、质量闸门
- **结果**: 成功
- **报告**: docs/UPDATE_LOG.md (§2026-05-24)

#### 部署 #3: Zero-Cost Intelligence Features (本次)
- **日期**: 2026-06-30 20:56-21:04 CST
- **目标**: <production-host> (192.0.2.10)
- **内容**: 海关供应链分析 + 智能情报聚合
- **结果**: 成功
- **报告**: N100_DEPLOYMENT_REPORT_2026-06-30.md

### 3.2 部署 #3 详细记录

```
开始时间: 20:56 CST
结束时间: 21:04 CST
总耗时: 8 分钟
执行者: Claude Code (Opus 4)
方法: rsync over SSH

步骤记录:
20:56 - 创建备份 (59MB)
20:57 - 同步代码 (347 files, 103,925 bytes)
20:57 - 环境变量验证 (ADMIN_API_TOKEN ✅, UPKUAJING ⚠️)
20:58 - 前端构建 (7.77s, 327.90 kB JS, 47.70 kB CSS)
20:58 - 服务重启 (API + Web)
20:58 - 服务验证 (both active)
20:59 - API 健康检查 (200 OK)
20:59 - 工具注册验证 (customs_supply_chain ✅)
21:00 - 情报聚合 API 测试 (200 OK, 10 contacts extracted)
21:04 - 部署完成
```

### 3.3 部署检查清单

每次部署前，请确认以下项目：

#### 部署前检查
- [ ] 代码已在本地测试通过
- [ ] `bash scripts/verify.sh` 全部通过
- [ ] 前端构建成功（无阻塞错误）
- [ ] 已阅读本次变更的 diff
- [ ] 已准备回滚方案

#### 部署步骤
- [ ] SSH 登录 <production-host>
- [ ] 创建备份
- [ ] 同步代码（git pull 或 rsync）
- [ ] 检查环境变量
- [ ] 安装新依赖（如有）
- [ ] 构建前端
- [ ] 重启服务
- [ ] 验证健康检查
- [ ] 测试新功能
- [ ] 检查日志无错误
- [ ] 创建部署报告

#### 部署后检查
- [ ] API: `http://192.0.2.10:8088/api/health` → 200
- [ ] Web: `http://192.0.2.10:3008/` → 200
- [ ] 新功能正常工作
- [ ] 日志无异常
- [ ] 数据库无损坏
- [ ] 备份已更新

### 3.4 回滚流程

```bash
#!/bin/bash
# 回滚到指定日期
# 用法: bash scripts/rollback.sh 20260630-205621

BACKUP_NAME="${1:-latest}"

echo "=== 情报官回滚 $BACKUP_NAME ==="

# 1. 停止服务
echo "1. 停止服务..."
systemctl --user stop osint-agent-network-api.service
systemctl --user stop osint-agent-network-web.service

# 2. 备份当前状态
echo "2. 备份当前状态..."
tar czf /var/backups/osint-agent-network/pre-rollback-$(date +%Y%m%d-%H%M%S).tar.gz \
  -C /opt/osint-agent-network . \
  --exclude=node_modules --exclude=__pycache__

# 3. 恢复备份
echo "3. 恢复备份..."
tar xzf /var/backups/osint-agent-network/backup-$BACKUP_NAME.tar.gz \
  -C /opt/osint-agent-network/

# 4. 构建前端
echo "4. 构建前端..."
cd /opt/osint-agent-network/frontend
npm run build

# 5. 启动服务
echo "5. 启动服务..."
systemctl --user start osint-agent-network-api.service
systemctl --user start osint-agent-network-web.service

# 6. 验证
echo "6. 验证..."
sleep 3
curl -sS http://127.0.0.1:8088/api/health

echo "=== 回滚完成 ==="
```

### 3.5 环境变量参考

```bash
# .env 文件模板
APP_PORT=8088
OSINT_DB_PATH=data/osint.sqlite
AGENT_API_TOKEN=<your-agent-token>
ADMIN_API_TOKEN=<your-admin-token>

# 模型中转
OSINT_LLM_BASE_URL=<llm-base-url>
OSINT_LLM_API_KEY=<llm-api-key>
OSINT_LLM_MODEL=<model-name>

# 跨境魔方海关 API（可选，用于供应链分析）
UPKUAJING_BASE_URL=https://saas.upkuajing.com
UPKUAJING_AUTHORIZATION=Bearer <your-token>
UPKUAJING_TIMEOUT_SECONDS=30

# 工具配置
COMPANY_NEWS_SOURCE=gnews
THEHARVESTER_PATH=/usr/local/bin/theHarvester
# ... 其他工具配置
```

---

## 四、运维手册（Operations Handbook）

### 4.1 系统架构（运行时）

```
┌──────────────────────────────────────────────────┐
│                    Web Browser                     │
│                 http://192.0.2.10:3008             │
└───────────────┬──────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────┐
│              Web UI (Vite + React)                │
│              Port: 3008                            │
│              Service: osint-agent-network-web     │
└───────────────┬──────────────────────────────────┘
                │ API Calls
                ▼
┌──────────────────────────────────────────────────┐
│              API Hub (Python http.server)         │
│              Port: 8088                            │
│              Service: osint-agent-network-api     │
└───────┬──────────────┬──────────────┬────────────┘
        │              │              │
        ▼              ▼              ▼
   ┌─────────┐  ┌──────────┐  ┌──────────────┐
   │ SQLite  │  │ Worker   │  │ Intel        │
   │ Store   │  │ Scheduler│  │ Gateway      │
   │         │  │          │  │ (Tool Plan)  │
   └─────────┘  └────┬─────┘  └──────┬───────┘
                     │               │
                     ▼               ▼
              ┌──────────────┐ ┌─────────────────┐
              │ Local Tools  │ │ External APIs    │
              │ (Sherlock,   │ │ (Upkuajing,     │
              │  theHarvester│ │  Panjiva, etc.) │
              │  etc.)       │ │                 │
              └──────────────┘ └─────────────────┘
```

### 4.2 服务配置（Systemd）

#### API 服务
```
文件: ~/.config/systemd/user/osint-agent-network-api.service

[Unit]
Description=OSINT Agent Network API
After=network.target

[Service]
WorkingDirectory=/opt/osint-agent-network
Environment="PYTHONPATH=backend"
EnvironmentFile=/opt/osint-agent-network/.env
ExecStart=/usr/bin/python3 -m app.main
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

#### Web 服务
```
文件: ~/.config/systemd/user/osint-agent-network-web.service

[Unit]
Description=OSINT Agent Network Web UI
After=osint-agent-network-api.service

[Service]
WorkingDirectory=/opt/osint-agent-network/frontend
ExecStart=/usr/bin/npm run preview --host 0.0.0.0 --port 3008
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

### 4.3 常见故障处理

#### 故障 1: API 服务启动失败
```bash
症状: systemctl status 显示 failed
原因: 端口被占用/Python 模块缺失/环境变量错误

诊断:
  ss -tlnp | grep 8088                          # 检查端口占用
  cd /opt/osint-agent-network
  PYTHONPATH=backend python3 -c "import app.main" # 检查导入

解决:
  # 杀掉占用进程
  kill -9 $(lsof -t -i:8088)
  # 重启服务
  systemctl --user restart osint-agent-network-api.service
```

#### 故障 2: 数据库锁定
```bash
症状: API 返回 "database is locked"
原因: 多个进程同时写入

诊断:
  lsof data/osint.sqlite                        # 查看谁在访问数据库

解决:
  # 重启 API 服务（强制释放锁）
  systemctl --user restart osint-agent-network-api.service
  # 如果持续出现，检查是否有多个 API 进程
  ps aux | grep "python.*app.main"
```

#### 故障 3: 前端资源 404
```bash
症状: 页面空白，控制台显示资源 404
原因: 前端未构建或构建产物路径不对

诊断:
  ls -l frontend/dist/assets/                   # 检查构建产物

解决:
  cd frontend
  npm run build                                  # 重新构建
  systemctl --user restart osint-agent-network-web.service
```

### 4.4 性能优化建议

1. **API 并发**: 提高 `http.server` 的线程池大小
2. **数据库索引**: 确保 `investigations` 表有 `(status, created_at)` 索引（已配置）
3. **静态资源**: 考虑使用 Nginx 反向代理静态文件
4. **工具超时**: 根据实际情况调整每个工具的 `default_timeout_seconds`

### 4.5 安全注意事项

1. **Token 管理**: 定期轮换 `AGENT_API_TOKEN` 和 `ADMIN_API_TOKEN`
2. **网络隔离**: 确保管理接口只能从内网访问
3. **输入验证**: 新增 API 端点必须添加输入验证
4. **凭证保护**: 不要在日志中打印 credentials
5. **HTTPS**: 如需公网访问，必须配置 SSL

---

## 五、联系方式与资源

### 项目资源
- **<production-host> 项目目录**: `/opt/osint-agent-network`
- **<production-host> 备份目录**: `/var/backups/osint-agent-network`
- **<production-host> 数据库**: `/opt/osint-agent-network/data/osint.sqlite`
- **本地项目目录**: `/path/to/osint-agent-network`

### 关键文档索引
| 文档 | 位置 | 说明 |
|------|------|------|
| 项目主文档 | README.md | 项目概述、快速启动 |
| 设计规范 | DESIGN.md | UI 视觉与交互规则 |
| 更新日志 | docs/UPDATE_LOG.md | 完整更新历史 |
| Agent 协议 | docs/AGENT_PROTOCOL.md | 外部 Agent 接入 |
| 供应链文档 | docs/CUSTOMS_SUPPLY_CHAIN.md | 海关供应链功能 |
| 情报聚合文档 | docs/INTELLIGENCE_AGGREGATION.md | 情报聚合功能 |
| <production-host> 部署手册 | docs/N100_DEPLOYMENT_RUNBOOK.md | 部署步骤 |
| 交付总结 | DELIVERY_SUMMARY_2026-06-30.md | 最新交付 |
| 部署报告 | N100_DEPLOYMENT_REPORT_2026-06-30.md | 最新部署详情 |
| 本文件 | PROJECT_CLOSURE_MAINTENANCE_LOG.md | 结尾/维护/部署综合日志 |

---

## 六、项目交接清单

当项目移交给新的维护者时，请确保以下内容已交接：

### 交接清单
- [ ] **源码目录**: `/opt/osint-agent-network` (<production-host>)
- [ ] **本地开发**: `/path/to/osint-agent-network` (Mac)
- [ ] **数据库**: `data/osint.sqlite` - 已有备份
- [ ] **环境变量**: `.env` 和 `.env.example` - Token 和 API Key
- [ ] **服务管理**: systemd 用户服务配置
- [ ] **备份机制**: 定时备份脚本和 systemd timer
- [ ] **监控脚本**: 健康检查、告警脚本
- [ ] **文档**: 所有 docs/ 和根目录 .md 文件
- [ ] **第三方 API**: 跨境魔方 Upkuajing 凭证
- [ ] **运行边界**: 仅用于授权公开来源信息整理
- [ ] **测试套件**: 单元测试、回归烟测、生产检查

### 需要移交的凭证
- [ ] `ADMIN_API_TOKEN`
- [ ] `AGENT_API_TOKEN`
- [ ] `UPKUAJING_AUTHORIZATION`（如有）
- [ ] `OSINT_LLM_API_KEY`（如有）

---

## 七、项目完结声明

本项目 `情报官 OSINT Agent Network` 已于 2026-06-30 完成 Zero-Cost Intelligence Features 阶段开发并部署到生产环境。

### 完成声明

**已完成**:
- ✅ 多 Agent 编排系统
- ✅ 10+ OSINT 工具适配器
- ✅ 23 位图谱展示
- ✅ 证据闭环系统
- ✅ Intelligence Core v3 (PIR/ACH/I&W/BLUF)
- ✅ 空白 Lead 逆向补全
- ✅ 海关供应链分析（零成本）
- ✅ 智能情报聚合（联系方式/社媒/产品）
- ✅ <production-host> 生产部署

**使用边界**: 本项目只用于授权范围内的公开来源信息整理、证据留痕和人工复核。

**预测边界**: IntelCore 预测层只输出判断、概率、风险场景和行动建议。

**许可边界**: 本项目以 GNU GPL v3 发布，SPDX 标识为 `GPL-3.0-only`。分发、修改和再分发必须遵守仓库根目录 `LICENSE`。

---

**本文档生效日期**: 2026-06-30  
**下次审查日期**: 2026-09-30  
**维护责任人**: 待确认  

---

*情报官 OSINT Agent Network - 面向授权公开信息调研的多 Agent 情报工作台*
