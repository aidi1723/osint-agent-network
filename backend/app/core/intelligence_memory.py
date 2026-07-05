from __future__ import annotations


CONFIRMED_ENTITY_TYPES = {
    "organization",
    "company",
    "brand",
    "business_scope",
    "product_scope",
    "production_base",
    "market_coverage",
    "domain",
    "email",
    "phone",
    "address",
    "declared_location",
    "likely_activity_region",
}

REVIEW_RELATIONSHIP_TOKENS = ("needs_review", "conflict", "image_claim")


def build_intelligence_memory(detail: dict) -> dict:
    entities = detail.get("entities", [])
    evidence = detail.get("evidence", [])
    relationships = detail.get("relationships", [])
    jobs = detail.get("jobs", [])

    confirmed_findings = [_finding_from_entity(item, evidence) for item in entities if _is_confirmed_entity(item)]
    review_findings = [_review_from_relationship(item) for item in relationships if _needs_review(item)]
    collection_gaps = _collection_gaps(entities, evidence, jobs)

    return {
        "coverage": {
            "confirmed_entities": len(confirmed_findings),
            "review_items": len(review_findings),
            "collection_gaps": len(collection_gaps),
            "evidence_items": len(evidence),
            "relationships": len(relationships),
        },
        "confirmed_findings": confirmed_findings,
        "review_findings": review_findings,
        "collection_gaps": collection_gaps,
        "directed_collection": [_directed_collection_item(gap, detail) for gap in collection_gaps],
    }


def _is_confirmed_entity(entity: dict) -> bool:
    entity_type = str(entity.get("type") or "")
    confidence = float(entity.get("confidence") or 0.0)
    return entity_type in CONFIRMED_ENTITY_TYPES and confidence >= 0.5


def _finding_from_entity(entity: dict, evidence: list[dict]) -> dict:
    value = str(entity.get("value") or "")
    return {
        "type": entity.get("type", "entity"),
        "value": value,
        "source_tool": entity.get("source_tool", ""),
        "confidence": float(entity.get("confidence") or 0.0),
        "evidence_count": sum(1 for item in evidence if item.get("entity_value") == value),
    }


def _needs_review(relationship: dict) -> bool:
    text = str(relationship.get("relationship_type") or "").lower()
    return any(token in text for token in REVIEW_RELATIONSHIP_TOKENS)


def _review_from_relationship(relationship: dict) -> dict:
    return {
        "from": relationship.get("from_value", ""),
        "to": relationship.get("to_value", ""),
        "relationship_type": relationship.get("relationship_type", ""),
        "confidence": float(relationship.get("confidence") or 0.0),
    }


def _collection_gaps(entities: list[dict], evidence: list[dict], jobs: list[dict]) -> list[dict]:
    entity_types = {str(item.get("type") or "") for item in entities}
    evidence_kinds = {str(item.get("evidence_kind") or "") for item in evidence}
    incomplete_jobs = {
        str(item.get("tool_name") or "")
        for item in jobs
        if str(item.get("status") or "") not in {"COMPLETED", "SKIPPED"}
    }
    gaps = []

    if not _has_decision_maker_signal(entities):
        gaps.append(
            {
                "key": "decision_maker",
                "label": "决策人",
                "reason": "未形成可确认的公开决策人姓名、职位或个人联系方式。",
                "related_jobs": _matching_jobs(incomplete_jobs, {"social_profile_search", "contact_discovery", "cross_verification"}),
            }
        )
    if not ({"news_article", "news_summary", "published_at"} & entity_types or "company_news_report" in evidence_kinds):
        gaps.append(
            {
                "key": "news",
                "label": "新闻/企业动态",
                "reason": "未形成可交叉验证的新闻报道、业务事件、采购信号或风险信号。",
                "related_jobs": _matching_jobs(incomplete_jobs, {"company_news", "company_news_monitoring"}),
            }
        )
    if not {"business_scope", "product_scope"} & entity_types:
        gaps.append(
            {
                "key": "business_scope",
                "label": "主营业务",
                "reason": "未形成结构化主营业务或产品系统节点。",
                "related_jobs": _matching_jobs(incomplete_jobs, {"company_osint", "analysis_judgement"}),
            }
        )
    if not {"production_base", "address", "declared_location", "likely_activity_region"} & entity_types:
        gaps.append(
            {
                "key": "operation_footprint",
                "label": "经营/制造足迹",
                "reason": "未形成结构化地址、区域运营点或制造基地节点。",
                "related_jobs": _matching_jobs(incomplete_jobs, {"company_osint", "supply_chain_mapping", "cross_verification"}),
            }
        )
    if "risk_signal" not in entity_types and not any(kind.endswith("_risk_signal") for kind in evidence_kinds):
        gaps.append(
            {
                "key": "risk_signals",
                "label": "风险信号",
                "reason": "未形成诉讼、处罚、负面新闻、来源冲突等结构化风险信号。",
                "related_jobs": _matching_jobs(incomplete_jobs, {"company_news_monitoring", "cross_verification", "analysis_judgement"}),
            }
        )
    return gaps


def _has_decision_maker_signal(entities: list[dict]) -> bool:
    for item in entities:
        entity_type = str(item.get("type") or "")
        confidence = float(item.get("confidence") or 0.0)
        if entity_type in {"decision_maker", "person", "profile_url"} and confidence >= 0.55:
            return True
        if entity_type == "identity" and confidence >= 0.7:
            return True
    return False


def _matching_jobs(incomplete_jobs: set[str], names: set[str]) -> list[str]:
    return sorted(incomplete_jobs & names)


def _directed_collection_item(gap: dict, detail: dict) -> dict:
    seed = str(detail.get("seed_value") or "")
    prompts = {
        "decision_maker": f"围绕 {seed} 查询公开工商登记、官网团队页、展会资料、LinkedIn/领英和新闻署名，寻找可交叉验证的负责人、销售负责人或区域负责人。",
        "news": f"围绕 {seed}、官网域名、关联公司名和制造基地名做约束新闻检索，抽取企业动态、合作、诉讼、召回、采购或扩产信号。",
        "business_scope": f"从官网、产品目录、第三方经销商和贸易平台抽取 {seed} 的主营产品系统、SKU 范围、目标车型和市场覆盖。",
        "operation_footprint": f"围绕 {seed} 的中国运营节点、制造基地、地址和公司名做工商/地图/官网交叉核验，区分自有工厂、合作厂和品牌宣传基地。",
        "risk_signals": f"围绕 {seed} 和关联主体检索处罚、诉讼、召回、贸易纠纷、品牌冒用和来源冲突，形成可追溯风险信号。",
    }
    return {
        "gap_key": gap["key"],
        "agent_focus": gap["label"],
        "prompt": prompts.get(gap["key"], f"继续围绕 {seed} 采集 {gap['label']} 相关公开证据。"),
        "related_jobs": gap.get("related_jobs", []),
    }
