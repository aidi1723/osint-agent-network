"""
产品情报聚合工具

从多个来源聚合产品信息：
- 企业官网产品目录
- 海关提单产品描述
- 新闻报道中的产品信息
- HS编码分析
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class ProductInfo:
    """产品信息"""
    name: str
    category: Optional[str] = None
    hs_code: Optional[str] = None
    description: Optional[str] = None
    source: str = ''
    mention_count: int = 1
    confidence: float = 0.0
    contexts: list[str] = None

    def __post_init__(self):
        if self.contexts is None:
            self.contexts = []


@dataclass
class ProductIntelligenceResult:
    """产品情报结果"""
    target: str
    products: list[ProductInfo]
    categories: list[str]
    hs_codes: list[str]
    total_products: int
    main_products: list[ProductInfo]  # 出现频次最高的主营产品
    brands: list[str]


class ProductIntelligenceAggregator:
    """产品情报聚合器"""

    def __init__(self):
        # 常见产品关键词模式
        self.product_keywords = [
            'aluminum', 'aluminium', 'steel', 'metal', 'plastic',
            'furniture', 'profile', 'extrusion', 'parts', 'components',
            'machinery', 'equipment', 'tool', 'material', 'product'
        ]

    def aggregate_from_data(
        self,
        entities: list[dict],
        evidence: list[dict],
        customs_data: Optional[dict] = None
    ) -> ProductIntelligenceResult:
        """
        从实体、证据、海关数据中聚合产品情报

        Args:
            entities: 实体列表
            evidence: 证据列表
            customs_data: 海关数据（可选）

        Returns:
            ProductIntelligenceResult
        """
        products = []
        brands = []
        hs_codes = []

        # 从证据中提取产品信息
        for ev in evidence:
            snippet = ev.get('snippet', '')
            source_tool = ev.get('source_tool', 'unknown')
            evidence_kind = ev.get('evidence_kind', '')

            # 新闻中的产品提及
            if evidence_kind in {'news_summary', 'business_event'}:
                extracted_products = self._extract_products_from_text(snippet)
                for product_name in extracted_products:
                    products.append(ProductInfo(
                        name=product_name,
                        source=source_tool,
                        confidence=0.6,
                        contexts=[snippet[:200]]
                    ))
            elif evidence_kind == 'trade_relationship':
                for product_name in self._extract_trade_products_from_snippet(snippet):
                    products.append(ProductInfo(
                        name=product_name,
                        category=self._categorize_product(product_name),
                        source=source_tool,
                        confidence=0.85 if source_tool == 'customs_supply_chain' else 0.7,
                        contexts=[snippet[:200]]
                    ))

        # 从海关数据中提取产品
        if customs_data:
            customs_products = self._extract_from_customs(customs_data)
            products.extend(customs_products)

        # 聚合同类产品
        products = self._aggregate_products(products)

        # 提取类别
        categories = list(set(p.category for p in products if p.category))

        # 提取HS编码
        hs_codes = list(set(p.hs_code for p in products if p.hs_code))

        # 识别主营产品（提及次数最多的前5个）
        main_products = sorted(products, key=lambda p: p.mention_count, reverse=True)[:5]

        return ProductIntelligenceResult(
            target='',
            products=products,
            categories=categories,
            hs_codes=hs_codes,
            total_products=len(products),
            main_products=main_products,
            brands=brands
        )

    def aggregate_from_customs_trades(self, trades: list[dict]) -> list[ProductInfo]:
        """
        从海关贸易记录中提取产品列表

        Args:
            trades: 海关贸易记录列表

        Returns:
            产品信息列表
        """
        product_counter = Counter()
        product_contexts = {}
        product_hs = {}

        for trade in trades:
            product = trade.get('product', '').strip()
            hs_code = trade.get('hsCode', '')

            if product:
                product_counter[product] += 1

                if product not in product_contexts:
                    product_contexts[product] = []

                context = f"海关记录: {trade.get('tradeDate', '')} - {trade.get('quantity', '')}"
                product_contexts[product].append(context)

                if hs_code and product not in product_hs:
                    product_hs[product] = hs_code

        products = []
        for product_name, count in product_counter.most_common(50):  # 最多50个产品
            products.append(ProductInfo(
                name=product_name,
                category=self._categorize_product(product_name),
                hs_code=product_hs.get(product_name),
                source='customs',
                mention_count=count,
                confidence=0.90,  # 海关数据可信度高
                contexts=product_contexts[product_name][:3]  # 最多3个上下文
            ))

        return products

    def _extract_products_from_text(self, text: str) -> list[str]:
        """从文本中提取产品名称（简化版）"""
        products = []
        text_lower = text.lower()

        # 查找包含产品关键词的短语
        for keyword in self.product_keywords:
            if keyword in text_lower:
                # 提取包含关键词的短语（前后各5个词）
                pattern = r'\b\w+\s+' * 5 + keyword + r'\s+\w+' * 5
                matches = re.findall(pattern, text_lower)
                for match in matches:
                    # 清理并提取核心产品名
                    words = match.split()
                    # 简化：取关键词前后各2个词
                    keyword_idx = words.index(keyword)
                    start = max(0, keyword_idx - 2)
                    end = min(len(words), keyword_idx + 3)
                    product_phrase = ' '.join(words[start:end])
                    products.append(product_phrase.title())

        return products[:10]  # 最多返回10个

    def _extract_from_customs(self, customs_data: dict) -> list[ProductInfo]:
        """从海关数据中提取产品"""
        products = []

        if 'downstream' in customs_data:
            customers = customs_data['downstream'].get('customers', [])
            for customer in customers:
                for product_name in customer.get('products', []):
                    products.append(ProductInfo(
                        name=product_name,
                        source='customs',
                        mention_count=customer.get('trade_count', 1),
                        confidence=0.85
                    ))

        if 'upstream' in customs_data:
            suppliers = customs_data['upstream'].get('suppliers', [])
            for supplier in suppliers:
                for product_name in supplier.get('products', []):
                    products.append(ProductInfo(
                        name=product_name,
                        source='customs',
                        mention_count=supplier.get('trade_count', 1),
                        confidence=0.85
                    ))

        return products

    def _extract_trade_products_from_snippet(self, snippet: str) -> list[str]:
        """从海关关系证据片段中提取产品列表。"""
        marker = '产品'
        if marker not in snippet:
            return []
        product_text = snippet.split(marker, 1)[1]
        product_text = product_text.lstrip('：: ').strip()
        product_text = re.split(r'[。；;]', product_text, maxsplit=1)[0]
        names = []
        for raw_name in re.split(r'[,，]', product_text):
            name = raw_name.strip().strip('. ').removesuffix('...')
            if name:
                names.append(name)
        return names[:20]

    def _aggregate_products(self, products: list[ProductInfo]) -> list[ProductInfo]:
        """聚合相似产品"""
        aggregated = {}

        for product in products:
            # 规范化产品名
            key = product.name.upper().strip()

            if key in aggregated:
                # 合并
                aggregated[key].mention_count += product.mention_count
                aggregated[key].contexts.extend(product.contexts)
                # 保留更高的置信度
                if product.confidence > aggregated[key].confidence:
                    aggregated[key].confidence = product.confidence
            else:
                aggregated[key] = product

        result = list(aggregated.values())
        result.sort(key=lambda p: p.mention_count, reverse=True)
        return result

    def _categorize_product(self, product_name: str) -> Optional[str]:
        """简单的产品分类"""
        name_lower = product_name.lower()

        categories = {
            'Metal Products': ['aluminum', 'aluminium', 'steel', 'metal', 'iron', 'copper'],
            'Plastic Products': ['plastic', 'polymer', 'resin'],
            'Furniture': ['furniture', 'chair', 'table', 'desk'],
            'Building Materials': ['profile', 'extrusion', 'panel', 'sheet', 'construction'],
            'Machinery': ['machinery', 'equipment', 'machine', 'tool'],
            'Parts & Components': ['parts', 'component', 'accessories', 'hardware'],
        }

        for category, keywords in categories.items():
            if any(kw in name_lower for kw in keywords):
                return category

        return 'Other'

    def format_for_display(self, result: ProductIntelligenceResult) -> dict:
        """格式化为前端显示格式"""
        return {
            'target': result.target,
            'products': [
                {
                    'name': p.name,
                    'category': p.category,
                    'hs_code': p.hs_code,
                    'description': p.description,
                    'source': p.source,
                    'mention_count': p.mention_count,
                    'confidence': p.confidence,
                    'contexts': p.contexts[:2]  # 最多2个上下文
                }
                for p in result.products
            ],
            'categories': result.categories,
            'hs_codes': result.hs_codes,
            'main_products': [
                {
                    'name': p.name,
                    'category': p.category,
                    'mention_count': p.mention_count,
                    'confidence': p.confidence
                }
                for p in result.main_products
            ],
            'brands': result.brands,
            'summary': {
                'total_products': result.total_products,
                'categories_count': len(result.categories),
                'hs_codes_count': len(result.hs_codes),
                'main_products_count': len(result.main_products)
            }
        }
