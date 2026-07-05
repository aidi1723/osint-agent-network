"""
海关数据供应链挖掘工具

基于跨境魔方海关API，通过反向查询实现：
- 查询供应商的所有下游客户
- 查询买家的所有上游供应商
- 统计贸易频次、产品类别、交易时间范围
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
from pathlib import Path

from app.core.normalization import normalize_target
from app.core.upkuajing_customs import UpkuajingCustomsClient, UpkuajingCustomsError
from app.tools.base import (
    NormalizedEntity,
    NormalizedEvidence,
    NormalizedRelationship,
    ParsedToolOutput,
)


@dataclass
class TradePartner:
    """贸易伙伴信息"""
    name: str
    country: str
    trade_count: int
    products: list[str]
    first_trade_date: str
    last_trade_date: str
    total_quantity: str
    relationship_type: str  # "customer" or "supplier"


class CustomsSupplyChainAdapter:
    """海关供应链分析适配器"""

    name = "customs_supply_chain"
    base_confidence = 0.85  # 海关数据可信度高

    def __init__(self, lookback_days: int = 730):
        """
        初始化

        Args:
            lookback_days: 回溯天数，默认730天(2年)
        """
        self.lookback_days = lookback_days
        self.client = UpkuajingCustomsClient()

    def validate_target(self, target_type: str, target_value: str) -> str:
        """验证目标类型"""
        if target_type not in {"company", "sparse_lead"}:
            raise ValueError(f"customs_supply_chain only accepts company targets, got {target_type}")
        return normalize_target("company", target_value)

    def find_downstream_customers(
        self,
        supplier_name: str,
        max_results: int = 50
    ) -> tuple[list[TradePartner], dict]:
        """
        查询供应商的所有下游客户

        Args:
            supplier_name: 供应商名称
            max_results: 最大返回结果数

        Returns:
            (客户列表, 原始API响应)
        """
        date_start = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")

        response = self.client.trade_list({
            "seller": supplier_name,
            "isExact": True,
            "dateStart": self._date_to_ms(date_start),
            "sorting_field": "tradeDate",
            "sorting_direction": "desc"
        })

        return self._parse_trade_partners(
            response,
            role="buyer",
            relationship_type="customer"
        ), response

    def find_upstream_suppliers(
        self,
        buyer_name: str,
        max_results: int = 50
    ) -> tuple[list[TradePartner], dict]:
        """
        查询买家的所有上游供应商

        Args:
            buyer_name: 买家名称
            max_results: 最大返回结果数

        Returns:
            (供应商列表, 原始API响应)
        """
        date_start = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")

        response = self.client.trade_list({
            "buyer": buyer_name,
            "isExact": True,
            "dateStart": self._date_to_ms(date_start),
            "sorting_field": "tradeDate",
            "sorting_direction": "desc"
        })

        return self._parse_trade_partners(
            response,
            role="seller",
            relationship_type="supplier"
        ), response

    def analyze_full_supply_chain(
        self,
        company_name: str
    ) -> ParsedToolOutput:
        """
        完整供应链分析：同时查询上游和下游

        Args:
            company_name: 公司名称

        Returns:
            ParsedToolOutput 包含所有实体、证据、关系
        """
        normalized_company = self.validate_target("company", company_name)

        # 查询下游客户
        customers, customer_response = self.find_downstream_customers(normalized_company)

        # 查询上游供应商
        suppliers, supplier_response = self.find_upstream_suppliers(normalized_company)

        # 转换为标准化输出
        entities: list[NormalizedEntity] = []
        evidence: list[NormalizedEvidence] = []
        relationships: list[NormalizedRelationship] = []

        # 目标公司实体
        entities.append(NormalizedEntity(
            type="company",
            value=normalized_company,
            source_tool=self.name,
            confidence=1.0
        ))

        # 处理下游客户
        for customer in customers:
            entities.append(NormalizedEntity(
                type="company",
                value=customer.name,
                source_tool=self.name,
                confidence=self.base_confidence
            ))

            evidence.append(NormalizedEvidence(
                entity_value=customer.name,
                evidence_kind="trade_relationship",
                source_tool=self.name,
                snippet=f"海关记录显示{customer.trade_count}次交易，产品：{', '.join(customer.products[:3])}..."
            ))

            relationships.append(NormalizedRelationship(
                from_value=normalized_company,
                to_value=customer.name,
                relationship_type="supplier_to_customer",
                confidence=self._calculate_confidence(customer.trade_count)
            ))

        # 处理上游供应商
        for supplier in suppliers:
            entities.append(NormalizedEntity(
                type="company",
                value=supplier.name,
                source_tool=self.name,
                confidence=self.base_confidence
            ))

            evidence.append(NormalizedEvidence(
                entity_value=supplier.name,
                evidence_kind="trade_relationship",
                source_tool=self.name,
                snippet=f"海关记录显示{supplier.trade_count}次交易，产品：{', '.join(supplier.products[:3])}..."
            ))

            relationships.append(NormalizedRelationship(
                from_value=supplier.name,
                to_value=normalized_company,
                relationship_type="supplier_to_customer",
                confidence=self._calculate_confidence(supplier.trade_count)
            ))

        return ParsedToolOutput(
            tool=self.name,
            target_type="company",
            target_value=normalized_company,
            entities=entities,
            evidence=evidence,
            relationships=relationships
        )

    def _parse_trade_partners(
        self,
        response: dict,
        role: str,
        relationship_type: str
    ) -> list[TradePartner]:
        """
        解析贸易伙伴信息

        Args:
            response: API响应
            role: "buyer" 或 "seller"
            relationship_type: "customer" 或 "supplier"

        Returns:
            贸易伙伴列表
        """
        if "data" not in response or "list" not in response["data"]:
            return []

        # 按伙伴名称聚合数据
        partners_data = {}

        for trade in response["data"]["list"]:
            partner_name = trade.get(role, "").strip()
            if not partner_name:
                continue

            if partner_name not in partners_data:
                partners_data[partner_name] = {
                    "name": partner_name,
                    "country": trade.get(f"{role}Country", ""),
                    "trades": [],
                    "products": set()
                }

            partners_data[partner_name]["trades"].append(trade)
            product = trade.get("product", "").strip()
            if product:
                partners_data[partner_name]["products"].add(product)

        # 转换为TradePartner对象
        partners = []
        for partner_name, data in partners_data.items():
            trades = data["trades"]
            products_list = list(data["products"])[:10]  # 最多保留10个产品

            # 计算总数量（尝试累加）
            total_quantity = "N/A"
            try:
                quantities = [float(t.get("quantity", 0)) for t in trades if t.get("quantity")]
                if quantities:
                    total_quantity = f"{sum(quantities):.2f}"
            except (ValueError, TypeError):
                pass

            partners.append(TradePartner(
                name=partner_name,
                country=data["country"],
                trade_count=len(trades),
                products=products_list,
                first_trade_date=trades[-1].get("tradeDate", ""),
                last_trade_date=trades[0].get("tradeDate", ""),
                total_quantity=total_quantity,
                relationship_type=relationship_type
            ))

        # 按交易次数排序
        partners.sort(key=lambda p: p.trade_count, reverse=True)

        return partners[:50]  # 最多返回50个

    def _calculate_confidence(self, trade_count: int) -> float:
        """
        根据交易次数计算置信度

        1次交易: 0.70
        2-5次: 0.80
        6-10次: 0.85
        11+次: 0.90
        """
        if trade_count >= 11:
            return 0.90
        elif trade_count >= 6:
            return 0.85
        elif trade_count >= 2:
            return 0.80
        else:
            return 0.70

    def _date_to_ms(self, date_str: str) -> int:
        """将日期字符串转换为毫秒时间戳"""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)
