from __future__ import annotations


FIELD_RULES = (
    ("company_identity", "企业名称", ("company", "organization"), 8),
    ("official_website", "官网/域名", ("domain", "website", "official_website", "url"), 8),
    ("contact_email", "企业邮箱", ("email",), 7),
    ("contact_phone", "电话/WhatsApp", ("phone", "whatsapp"), 7),
    ("operation_location", "地址/经营区域", ("address", "declared_location", "likely_activity_region", "country_region"), 7),
    ("business_scope", "主营业务", ("business_scope", "product_scope", "purchase_category"), 8),
    ("decision_maker", "决策人候选", ("identity", "decision_maker", "person", "profile_url"), 6),
    ("relationships", "关系链", (), 8),
    ("evidence_ledger", "证据账本", (), 10),
    ("fact_pool", "事实池", (), 10),
    ("pir_requirements", "PIR/EEI 情报需求", (), 8),
    ("cross_verification", "交叉验证矩阵", (), 10),
    ("accepted_facts", "已采纳事实", (), 10),
    ("ach", "ACH 假说", (), 8),
    ("bluf_report", "BLUF 报告", (), 13),
)

COMPLETION_MIN_SCORE = 72
COMPLETION_REQUIRED_KEYS = {
    "company_identity",
    "evidence_ledger",
    "fact_pool",
    "bluf_report",
    "pir_requirements",
    "cross_verification",
}
BUSINESS_CLOSURE_REQUIRED_KEYS = {
    "official_website",
    "business_scope",
    "decision_maker",
}


def build_quality_assessment(detail: dict) -> dict:
    entities = detail.get("entities") or []
    entity_types = {str(item.get("type") or "") for item in entities}
    report_markdown = str(detail.get("report_markdown") or "")
    checks = []

    for key, label, accepted_types, weight in FIELD_RULES:
        present = _present(key, accepted_types, detail, entity_types, report_markdown)
        checks.append(
            {
                "key": key,
                "label": label,
                "present": present,
                "weight": weight,
                "score": weight if present else 0,
                "reason": _reason(key, label, present),
            }
        )

    total_weight = sum(item["weight"] for item in checks)
    earned = sum(item["score"] for item in checks)
    score = round((earned / total_weight) * 100, 1) if total_weight else 0.0
    missing = [item for item in checks if not item["present"]]
    missing_keys = [item["key"] for item in missing]
    blocking_keys = _blocking_keys(missing_keys)
    completion_ready = score >= COMPLETION_MIN_SCORE and not blocking_keys

    return {
        "score": score,
        "completion_ready": completion_ready,
        "minimum_score": COMPLETION_MIN_SCORE,
        "missing_keys": missing_keys,
        "blocking_keys": blocking_keys,
        "checks": checks,
    }


def _blocking_keys(missing_keys: list[str]) -> list[str]:
    missing = set(missing_keys)
    blocking = set(COMPLETION_REQUIRED_KEYS & missing)
    blocking.update(BUSINESS_CLOSURE_REQUIRED_KEYS & missing)
    if {"contact_email", "contact_phone"} <= missing:
        blocking.add("contact_channel")
    return sorted(blocking)


def completion_status_for_detail(detail: dict, requested_status: str) -> str:
    if requested_status != "COMPLETED":
        return requested_status
    assessment = build_quality_assessment(detail)
    return "COMPLETED" if assessment["completion_ready"] else "NEEDS_REVIEW"


def render_structured_report(detail: dict, assessment: dict | None = None) -> str:
    assessment = assessment or build_quality_assessment(detail)
    facts = detail.get("facts") or []
    evidence_ledger = detail.get("evidence_ledger") or []
    requirements = detail.get("intelligence_requirements") or {}
    matrix = detail.get("cross_verification_matrix") or []
    gaps = ((detail.get("intelligence_memory") or {}).get("collection_gaps") or [])
    directed = ((detail.get("intelligence_memory") or {}).get("directed_collection") or [])
    analysis = detail.get("hypothesis_analysis") or {}

    lines = [
        f"# {detail.get('name') or detail.get('seed_value') or '情报评估报告'}",
        "",
        "## BLUF",
        _bluf_text(detail, assessment),
        "",
        "## PIR 逐项回答",
    ]
    pirs = requirements.get("pirs") or []
    if pirs:
        for pir in pirs[:6]:
            confidence = _format_confidence(pir.get("confidence"))
            answer = pir.get("answer") or "尚未形成完整回答。"
            lines.append(f"- [{pir.get('status', 'OPEN')} / {confidence}] {pir.get('question', '')}：{answer}")
    else:
        lines.append("- 未定义 PIR，当前报告按默认调查目标解释。")

    lines.extend([
        "",
        "## 质量闸门",
        f"- 完整度评分：{assessment['score']} / 100",
        f"- 完成状态：{'可完成' if assessment['completion_ready'] else '需要复核'}",
    ])
    if assessment["missing_keys"]:
        missing_labels = [
            item["label"]
            for item in assessment["checks"]
            if item["key"] in set(assessment["missing_keys"])
        ]
        lines.append(f"- 缺口：{'、'.join(missing_labels)}")

    lines.extend(["", "## EEI 覆盖摘要"])
    eeis = requirements.get("eeis") or []
    if eeis:
        for eei in eeis[:10]:
            required = "必需" if eei.get("required") else "可选"
            lines.append(f"- [{eei.get('status', 'MISSING')} / {required}] {eei.get('label', '')}")
    else:
        lines.append("- 未定义 EEI。")

    lines.extend(["", "## 交叉验证矩阵摘要"])
    if matrix:
        for row in matrix[:10]:
            value = row.get("candidate_value") or "待补充"
            lines.append(f"- [{row.get('status', 'MISSING')}] {row.get('label', row.get('field_key'))}：{value}。{row.get('rationale', '')}")
    else:
        lines.append("- 暂无交叉验证矩阵。")

    lines.extend(["", "## 已确认事实"])
    if facts:
        for fact in facts[:12]:
            status = fact.get("status", "NEEDS_REVIEW")
            confidence = _format_confidence(fact.get("confidence"))
            admiralty = fact.get("admiralty_code") or "未评级"
            lines.append(f"- [{status} / {admiralty} / {confidence}] {fact.get('statement', '')}")
    else:
        lines.append("- 暂无事实池记录，不能把当前结果视为成熟结论。")

    lines.extend(["", "## 证据附录"])
    if evidence_ledger:
        for record in evidence_ledger[:10]:
            source = record.get("source_url") or record.get("source_type") or "未知来源"
            admiralty = record.get("admiralty_code") or "未评级"
            snippet = record.get("snippet") or source
            lines.append(f"- [{admiralty}] {snippet} ({source})")
    else:
        lines.append("- 暂无证据账本记录。")

    lines.extend(["", "## ACH / 假说"])
    likely = analysis.get("most_likely_hypothesis") or ""
    language = analysis.get("confidence_language") or ""
    if likely or language:
        lines.append(f"- 最可能假说：{likely or '未指定'}")
        if language:
            lines.append(f"- 估计语言：{language}")
    else:
        lines.append("- 暂无 ACH 评分结果。")

    lines.extend(["", "## I&W 征候"])
    for item in _indicator_lines(detail, matrix):
        lines.append(f"- {item}")

    lines.extend(["", "## 情报缺口"])
    if gaps:
        for gap in gaps[:8]:
            lines.append(f"- {gap.get('label', '缺口')}：{gap.get('reason', '')}")
    else:
        lines.append("- 暂无显著缺口。")

    lines.extend(["", "## 下一步动作"])
    if directed:
        for item in directed[:8]:
            lines.append(f"- {item.get('agent_focus', '继续采集')}：{item.get('prompt', '')}")
    else:
        lines.append("- 继续补齐缺失来源并执行交叉验证。")

    return "\n".join(lines).strip() + "\n"


def _present(key: str, accepted_types: tuple[str, ...], detail: dict, entity_types: set[str], report_markdown: str) -> bool:
    if key == "decision_maker":
        return _has_decision_maker_signal(detail.get("entities") or [])
    if accepted_types:
        return bool(entity_types & set(accepted_types))
    if key == "relationships":
        return bool(detail.get("relationships"))
    if key == "evidence_ledger":
        return bool(detail.get("evidence_ledger"))
    if key == "fact_pool":
        return bool(detail.get("facts"))
    if key == "pir_requirements":
        req = detail.get("intelligence_requirements") or {}
        return bool(req.get("pirs") and req.get("eeis"))
    if key == "cross_verification":
        matrix = detail.get("cross_verification_matrix") or []
        return any(item.get("status") in {"CONFIRMED", "LIKELY", "SUPPORTED"} for item in matrix)
    if key == "accepted_facts":
        return any(
            item.get("promotion_stage") == "ACCEPTED_FACT" or item.get("status") in {"CONFIRMED", "LIKELY"}
            for item in detail.get("facts") or []
        )
    if key == "ach":
        analysis = detail.get("hypothesis_analysis") or {}
        return bool(detail.get("hypotheses") or analysis.get("most_likely_hypothesis"))
    if key == "bluf_report":
        return "bluf" in report_markdown.lower() and len(report_markdown.strip()) >= 20
    return False


def _has_decision_maker_signal(entities: list[dict]) -> bool:
    for item in entities:
        entity_type = str(item.get("type") or "")
        confidence = float(item.get("confidence") or 0.0)
        if entity_type in {"decision_maker", "person", "profile_url"} and confidence >= 0.55:
            return True
        if entity_type == "identity" and confidence >= 0.7:
            return True
    return False


def _reason(key: str, label: str, present: bool) -> str:
    if present:
        return f"{label} 已形成结构化记录。"
    return f"{label} 未形成结构化记录或证据不足。"


def _bluf_text(detail: dict, assessment: dict) -> str:
    if detail.get("summary"):
        return str(detail["summary"])
    seed = detail.get("seed_value") or "当前目标"
    if assessment["completion_ready"]:
        return f"{seed} 已达到基础情报闭环，可以进入人工复核和业务动作阶段。"
    return f"{seed} 尚未达到完成闸门，当前结论应按候选情报处理。"


def _format_confidence(value) -> str:
    if value is None:
        return "置信度未标注"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "置信度未标注"


def _indicator_lines(detail: dict, matrix: list[dict]) -> list[str]:
    positive = []
    risk = []
    statuses = {row.get("field_key"): row.get("status") for row in matrix}
    if statuses.get("company_identity") in {"CONFIRMED", "LIKELY"}:
        positive.append("企业身份存在较强公开来源支撑。")
    if statuses.get("contact_email") in {"CONFIRMED", "LIKELY", "SUPPORTED"} or statuses.get("contact_phone") in {"CONFIRMED", "LIKELY", "SUPPORTED"}:
        positive.append("至少一个联系渠道具备公开证据支撑。")
    if statuses.get("purchase_intent") in {"CONFIRMED", "LIKELY", "SUPPORTED"}:
        positive.append("存在采购意图或业务匹配征候。")
    if any(row.get("status") == "CONFLICTED" for row in matrix):
        risk.append("存在字段冲突，需要人工复核。")
    if not positive:
        positive.append("暂未形成强采购或身份闭合征候。")
    return [f"正向：{item}" for item in positive[:4]] + [f"风险：{item}" for item in risk[:4]]
