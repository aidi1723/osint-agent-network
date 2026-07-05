#!/bin/bash
# 海关供应链功能验证脚本
# 使用方法: bash scripts/verify_supply_chain.sh

set -e

echo "=========================================="
echo "海关供应链功能验证"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. 检查文件是否存在
echo "1. 检查文件完整性..."
files=(
    "backend/app/tools/customs_supply_chain.py"
    "backend/tests/test_customs_supply_chain.py"
    "frontend/src/components/SupplyChainPanel.tsx"
    "docs/CUSTOMS_SUPPLY_CHAIN.md"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "  ${GREEN}✓${NC} $file"
    else
        echo -e "  ${RED}✗${NC} $file (缺失)"
        exit 1
    fi
done
echo ""

# 2. 运行单元测试
echo "2. 运行单元测试..."
cd "$(dirname "$0")/.."
if PYTHONPATH=backend python3 -m unittest backend.tests.test_customs_supply_chain 2>&1 | grep -q "OK"; then
    echo -e "  ${GREEN}✓${NC} 单元测试通过"
else
    echo -e "  ${RED}✗${NC} 单元测试失败"
    exit 1
fi
echo ""

# 3. 检查工具注册
echo "3. 检查工具注册..."
if grep -q "customs_supply_chain" backend/app/core/registry.py; then
    echo -e "  ${GREEN}✓${NC} 工具已注册到registry"
else
    echo -e "  ${RED}✗${NC} 工具未注册"
    exit 1
fi
echo ""

# 4. 检查API接口
echo "4. 检查API接口..."
if grep -q "/api/customs/supply-chain" backend/app/main.py; then
    echo -e "  ${GREEN}✓${NC} API接口已添加"
else
    echo -e "  ${RED}✗${NC} API接口未添加"
    exit 1
fi
echo ""

# 5. 检查前端集成
echo "5. 检查前端集成..."
if grep -q "SupplyChainPanel" frontend/src/main.tsx; then
    echo -e "  ${GREEN}✓${NC} 前端组件已集成"
else
    echo -e "  ${RED}✗${NC} 前端组件未集成"
    exit 1
fi
echo ""

# 6. 检查环境变量
echo "6. 检查环境变量配置..."
if [ -f ".env" ]; then
    if grep -q "UPKUAJING_AUTHORIZATION" .env; then
        if [ -z "$(grep UPKUAJING_AUTHORIZATION .env | cut -d'=' -f2)" ]; then
            echo -e "  ${YELLOW}⚠${NC} UPKUAJING_AUTHORIZATION已配置但为空"
        else
            echo -e "  ${GREEN}✓${NC} UPKUAJING_AUTHORIZATION已配置"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} UPKUAJING_AUTHORIZATION未在.env中配置"
    fi

    if grep -q "ADMIN_API_TOKEN" .env; then
        echo -e "  ${GREEN}✓${NC} ADMIN_API_TOKEN已配置"
    else
        echo -e "  ${YELLOW}⚠${NC} ADMIN_API_TOKEN未配置（建议配置）"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} .env文件不存在"
fi
echo ""

# 7. 测试前端构建
echo "7. 测试前端构建..."
cd frontend
if npm run build > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} 前端构建成功"
else
    echo -e "  ${RED}✗${NC} 前端构建失败"
    exit 1
fi
cd ..
echo ""

echo "=========================================="
echo -e "${GREEN}所有检查通过！${NC}"
echo "=========================================="
echo ""
echo "下一步操作:"
echo "1. 启动后端: PYTHONPATH=backend python3 -m app.main"
echo "2. 启动前端: cd frontend && npm run dev"
echo "3. 访问: http://127.0.0.1:3008"
echo "4. 创建公司类型调查任务"
echo "5. 点击'分析供应链'按钮"
echo ""
echo "详细文档: docs/CUSTOMS_SUPPLY_CHAIN.md"
