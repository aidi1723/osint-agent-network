from __future__ import annotations

from hashlib import sha1

from app.core.osint_fusion import signal_metadata_by_value


SEED_NODE_ID = "seed:target"


def build_investigation_graph(detail: dict) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    node_ids: set[str] = set()
    edge_ids: set[str] = set()
    value_to_node: dict[str, str] = {}
    osint_metadata = signal_metadata_by_value(detail)

    def add_node(node: dict) -> str:
        node_id = node["id"]
        if node_id not in node_ids:
            node_ids.add(node_id)
            nodes.append(node)
        value = str(node.get("value") or "")
        if value and value not in value_to_node:
            value_to_node[value] = node_id
        return node_id

    def add_edge(edge: dict) -> None:
        edge_id = edge["id"]
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            return
        if edge_id in edge_ids:
            return
        edge_ids.add(edge_id)
        edges.append(edge)

    def add_source_node(source_tool: str) -> str | None:
        source = str(source_tool or "").strip()
        if not source:
            return None
        source_id = _node_id("source", "tool", source)
        add_node(
            {
                "id": source_id,
                "label": _short_label(source, limit=28),
                "type": "source",
                "value": source,
                "source_tool": source,
                "confidence": 0.0,
                "risk_level": "",
                "evidence_count": 0,
                "metadata": {"source_kind": _source_kind(source)},
            }
        )
        return source_id

    seed_value = str(detail.get("seed_value") or "").strip()
    seed_type = str(detail.get("seed_type") or "seed").strip() or "seed"
    add_node(
        {
            "id": SEED_NODE_ID,
            "label": seed_value or "seed",
            "type": "seed",
            "value": seed_value,
            "source_tool": "investigation",
            "confidence": 1.0,
            "risk_level": "",
            "evidence_count": 0,
            "metadata": {"seed_type": seed_type},
        }
    )
    if seed_value and seed_type == "company":
        company_node_id = _node_id("entity", "organization", seed_value)
        add_node(
            {
                "id": company_node_id,
                "label": _short_label(seed_value),
                "type": "entity",
                "value": seed_value,
                "source_tool": "investigation",
                "confidence": 1.0,
                "risk_level": "",
                "evidence_count": 0,
                "metadata": {"entity_type": "organization"},
            }
        )
        add_edge(
            {
                "id": _edge_id(SEED_NODE_ID, company_node_id, "seed_identifies_company"),
                "from": SEED_NODE_ID,
                "to": company_node_id,
                "label": "目标企业",
                "type": "seed_identifies_company",
                "confidence": 1.0,
                "source": "investigation",
            }
        )

    for entity in detail.get("entities", []):
        entity_value = str(entity.get("value") or "").strip()
        if not entity_value:
            continue
        source_node = add_source_node(entity.get("source_tool", ""))
        node_id = _node_id("entity", entity.get("type", "entity"), entity_value)
        add_node(
            {
                "id": node_id,
                "label": _short_label(entity_value),
                "type": "entity",
                "value": entity_value,
                "source_tool": entity.get("source_tool", ""),
                "confidence": float(entity.get("confidence") or 0.0),
                "risk_level": "",
                "evidence_count": _evidence_count(entity_value, detail.get("evidence", [])),
                "metadata": {
                    "entity_type": entity.get("type", "entity"),
                    **osint_metadata.get(entity_value, {}),
                },
            }
        )
        if source_node:
            add_edge(
                {
                    "id": _edge_id(source_node, node_id, "source_emitted_entity"),
                    "from": source_node,
                    "to": node_id,
                    "label": "信息来源",
                    "type": "source_emitted_entity",
                    "confidence": float(entity.get("confidence") or 0.0),
                    "source": entity.get("source_tool", ""),
                }
            )
        if entity_value == seed_value:
            add_edge(
                {
                    "id": _edge_id(SEED_NODE_ID, node_id, "seed_matches_entity"),
                    "from": SEED_NODE_ID,
                    "to": node_id,
                    "label": "初始线索",
                    "type": "seed_matches_entity",
                    "confidence": 1.0,
                    "source": "investigation",
                }
            )

    for relationship in detail.get("relationships", []):
        from_node = value_to_node.get(str(relationship.get("from_value") or ""))
        to_node = value_to_node.get(str(relationship.get("to_value") or ""))
        if not from_node or not to_node:
            continue
        relationship_type = str(relationship.get("relationship_type") or "related_to")
        relationship_edge_id = _edge_id(from_node, to_node, relationship_type)
        add_edge(
            {
                "id": relationship_edge_id,
                "from": from_node,
                "to": to_node,
                "label": relationship_type,
                "type": relationship_type,
                "confidence": float(relationship.get("confidence") or 0.0),
                "source": "relationship",
            }
        )
        source_node = _relationship_source_node(
            relationship,
            detail.get("evidence", []),
            detail.get("entities", []),
            value_to_node,
            add_source_node,
        )
        if source_node:
            add_edge(
                {
                    "id": _edge_id(source_node, from_node, f"supports_relationship:{relationship_edge_id}"),
                    "from": source_node,
                    "to": from_node,
                    "label": "关系来源",
                    "type": "supports_relationship",
                    "confidence": float(relationship.get("confidence") or 0.0),
                    "source": str(
                        relationship.get("source_tool")
                        or _relationship_source_tool(relationship, detail.get("evidence", []))
                        or _relationship_entity_source_tool(relationship, detail.get("entities", []))
                        or ""
                    ),
                    "metadata": {"relationship_edge_id": relationship_edge_id},
                }
            )

    for evidence in detail.get("evidence", []):
        entity_value = str(evidence.get("entity_value") or "").strip()
        target_node = value_to_node.get(entity_value)
        if not target_node:
            continue
        source_node = add_source_node(evidence.get("source_tool", ""))
        evidence_id = _node_id("evidence", evidence.get("evidence_kind", "evidence"), entity_value)
        add_node(
            {
                "id": evidence_id,
                "label": _short_label(str(evidence.get("snippet") or entity_value)),
                "type": "evidence",
                "value": entity_value,
                "source_tool": evidence.get("source_tool", ""),
                "confidence": 0.0,
                "risk_level": "",
                "evidence_count": 0,
                "metadata": {
                    "evidence_kind": evidence.get("evidence_kind", "evidence"),
                    "snippet": evidence.get("snippet", ""),
                    **osint_metadata.get(entity_value, {}),
                },
            }
        )
        add_edge(
            {
                "id": _edge_id(evidence_id, target_node, "supports_entity"),
                "from": evidence_id,
                "to": target_node,
                "label": "证据支持",
                "type": "supports_entity",
                "confidence": 0.0,
                "source": evidence.get("source_tool", ""),
            }
        )
        if source_node:
            add_edge(
                {
                    "id": _edge_id(source_node, evidence_id, "source_emitted_evidence"),
                    "from": source_node,
                    "to": evidence_id,
                    "label": "信息来源",
                    "type": "source_emitted_evidence",
                    "confidence": 0.0,
                    "source": evidence.get("source_tool", ""),
                }
            )

    ledger_node_by_id: dict[str, str] = {}
    for record in detail.get("evidence_ledger", []):
        evidence_id = str(record.get("id") or "").strip()
        if not evidence_id:
            continue
        source_node = add_source_node(record.get("source_tool", ""))
        ledger_node_id = _node_id("evidence-ledger", evidence_id, record.get("content_hash") or evidence_id)
        ledger_node_by_id[evidence_id] = ledger_node_id
        add_node(
            {
                "id": ledger_node_id,
                "label": _short_label(str(record.get("source_url") or evidence_id), limit=36),
                "type": "evidence_ledger",
                "value": str(record.get("source_url") or evidence_id),
                "source_tool": record.get("source_tool", ""),
                "confidence": _admiralty_confidence(record.get("admiralty_code", "")),
                "risk_level": "",
                "evidence_count": 0,
                "metadata": {
                    "evidence_id": evidence_id,
                    "source_type": record.get("source_type", ""),
                    "admiralty_code": record.get("admiralty_code", ""),
                    "snippet": record.get("snippet", ""),
                    "observed_at": record.get("observed_at", ""),
                },
            }
        )
        if source_node:
            add_edge(
                {
                    "id": _edge_id(source_node, ledger_node_id, "source_emitted_evidence_ledger"),
                    "from": source_node,
                    "to": ledger_node_id,
                    "label": "信息来源",
                    "type": "source_emitted_evidence_ledger",
                    "confidence": _admiralty_confidence(record.get("admiralty_code", "")),
                    "source": record.get("source_tool", ""),
                }
            )

    for fact in detail.get("facts", []):
        fact_id = str(fact.get("id") or "").strip()
        if not fact_id:
            continue
        object_value = str(fact.get("object") or "").strip()
        fact_node_id = _node_id("fact", fact_id, fact.get("statement") or fact_id)
        add_node(
            {
                "id": fact_node_id,
                "label": _short_label(str(fact.get("statement") or fact_id), limit=40),
                "type": "fact",
                "value": str(fact.get("statement") or fact_id),
                "source_tool": "fact_pool",
                "confidence": float(fact.get("confidence") or 0.0),
                "risk_level": "",
                "evidence_count": len(fact.get("evidence_ids") or []),
                "metadata": {
                    "fact_id": fact_id,
                    "subject": fact.get("subject", ""),
                    "predicate": fact.get("predicate", ""),
                    "status": fact.get("status", ""),
                    "admiralty_code": fact.get("admiralty_code", ""),
                    "object": object_value,
                    "valid_from": fact.get("valid_from", ""),
                    "valid_to": fact.get("valid_to"),
                },
            }
        )
        if object_value and object_value not in value_to_node:
            object_node_id = _node_id("fact-object", fact.get("predicate", "object"), object_value)
            add_node(
                {
                    "id": object_node_id,
                    "label": _short_label(object_value),
                    "type": "entity",
                    "value": object_value,
                    "source_tool": "fact_pool",
                    "confidence": float(fact.get("confidence") or 0.0),
                    "risk_level": "",
                    "evidence_count": len(fact.get("evidence_ids") or []),
                    "metadata": {"entity_type": _entity_type_from_predicate(fact.get("predicate", ""))},
                }
            )
        object_node = value_to_node.get(object_value)
        if object_node:
            add_edge(
                {
                    "id": _edge_id(fact_node_id, object_node, "fact_has_object"),
                    "from": fact_node_id,
                    "to": object_node,
                    "label": str(fact.get("predicate") or "事实对象"),
                    "type": "fact_has_object",
                    "confidence": float(fact.get("confidence") or 0.0),
                    "source": "fact_pool",
                }
            )
        subject_node = value_to_node.get(str(fact.get("subject") or "")) or SEED_NODE_ID
        add_edge(
            {
                "id": _edge_id(subject_node, fact_node_id, "subject_has_fact"),
                "from": subject_node,
                "to": fact_node_id,
                "label": "确认事实",
                "type": "subject_has_fact",
                "confidence": float(fact.get("confidence") or 0.0),
                "source": "fact_pool",
            }
        )
        for evidence_id in fact.get("evidence_ids") or []:
            ledger_node = ledger_node_by_id.get(str(evidence_id))
            if ledger_node:
                add_edge(
                    {
                        "id": _edge_id(ledger_node, fact_node_id, "evidence_supports_fact"),
                        "from": ledger_node,
                        "to": fact_node_id,
                        "label": "证据支持",
                        "type": "evidence_supports_fact",
                        "confidence": float(fact.get("confidence") or 0.0),
                        "source": "evidence_ledger",
                    }
                )

    for hypothesis in detail.get("hypotheses", []):
        hypothesis_id = str(hypothesis.get("id") or "").strip()
        if not hypothesis_id:
            continue
        status = str(hypothesis.get("status") or "")
        hypothesis_node_id = _node_id("hypothesis", hypothesis_id, hypothesis.get("statement") or hypothesis_id)
        add_node(
            {
                "id": hypothesis_node_id,
                "label": _short_label(str(hypothesis.get("statement") or hypothesis_id), limit=40),
                "type": "hypothesis",
                "value": str(hypothesis.get("statement") or hypothesis_id),
                "source_tool": "hypothesis_pool",
                "confidence": float(hypothesis.get("support_score") or 0.0),
                "risk_level": "medium" if status in {"DISFAVORED", "REJECTED"} else "",
                "evidence_count": len(hypothesis.get("supporting_evidence") or [])
                + len(hypothesis.get("contradictory_evidence") or []),
                "metadata": {
                    "hypothesis_id": hypothesis_id,
                    "status": status,
                    "support_score": hypothesis.get("support_score", 0.0),
                    "inconsistency_score": hypothesis.get("inconsistency_score", 0.0),
                    "mutually_exclusive_group": hypothesis.get("mutually_exclusive_group", "default"),
                },
            }
        )
        add_edge(
            {
                "id": _edge_id(hypothesis_node_id, SEED_NODE_ID, "hypothesis_attached_to_seed"),
                "from": hypothesis_node_id,
                "to": SEED_NODE_ID,
                "label": "分析假说",
                "type": "hypothesis_attached_to_seed",
                "confidence": float(hypothesis.get("support_score") or 0.0),
                "source": "hypothesis_pool",
            }
        )

    for index, signal in enumerate((detail.get("risk_report") or {}).get("top_risk_signals", [])):
        signal_id = _node_id("risk", signal.get("kind", "risk"), str(index))
        severity = str(signal.get("severity") or "low")
        add_node(
            {
                "id": signal_id,
                "label": str(signal.get("kind") or "risk_signal"),
                "type": "risk_signal",
                "value": str(signal.get("summary") or ""),
                "source_tool": "risk_report",
                "confidence": 0.0,
                "risk_level": severity,
                "evidence_count": len(signal.get("evidence_values") or []),
                "metadata": {
                    "severity": severity,
                    "summary": signal.get("summary", ""),
                    "evidence_values": signal.get("evidence_values") or [],
                },
            }
        )
        linked = False
        for evidence_value in signal.get("evidence_values") or []:
            target_node = value_to_node.get(str(evidence_value))
            if not target_node:
                continue
            linked = True
            add_edge(
                {
                    "id": _edge_id(signal_id, target_node, "risk_supported_by"),
                    "from": signal_id,
                    "to": target_node,
                    "label": "风险依据",
                    "type": "risk_supported_by",
                    "confidence": 0.0,
                    "source": "risk_report",
                }
            )
        if not linked:
            add_edge(
                {
                    "id": _edge_id(signal_id, SEED_NODE_ID, "risk_attached_to_seed"),
                    "from": signal_id,
                    "to": SEED_NODE_ID,
                    "label": "待复核",
                    "type": "risk_attached_to_seed",
                    "confidence": 0.0,
                    "source": "risk_report",
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "nodes": len(nodes),
            "edges": len(edges),
            "risk_nodes": sum(1 for node in nodes if node["type"] == "risk_signal"),
            "evidence_nodes": sum(1 for node in nodes if node["type"] == "evidence"),
            "evidence_ledger_nodes": sum(1 for node in nodes if node["type"] == "evidence_ledger"),
            "fact_nodes": sum(1 for node in nodes if node["type"] == "fact"),
            "hypothesis_nodes": sum(1 for node in nodes if node["type"] == "hypothesis"),
            "source_nodes": sum(1 for node in nodes if node["type"] == "source"),
            "osint_signal_nodes": sum(
                1 for node in nodes if node.get("metadata", {}).get("core_axis")
            ),
            "memory_findings": len(
                (detail.get("intelligence_memory") or {}).get("confirmed_findings", [])
            ),
            "collection_gaps": len(
                (detail.get("intelligence_memory") or {}).get("collection_gaps", [])
            ),
        },
    }


def _node_id(prefix: str, kind: str, value: str) -> str:
    return f"{prefix}:{_digest(f'{kind}:{value}')}"


def _edge_id(from_node: str, to_node: str, edge_type: str) -> str:
    return f"edge:{_digest(f'{from_node}:{to_node}:{edge_type}')}"


def _digest(value: str) -> str:
    return sha1(value.encode("utf-8")).hexdigest()[:16]


def _evidence_count(value: str, evidence_items: list[dict]) -> int:
    return sum(1 for item in evidence_items if item.get("entity_value") == value)


def _short_label(value: str, limit: int = 42) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _relationship_source_tool(relationship: dict, evidence_items: list[dict]) -> str:
    endpoints = {
        str(relationship.get("from_value") or ""),
        str(relationship.get("to_value") or ""),
    }
    for item in evidence_items:
        if str(item.get("entity_value") or "") in endpoints and item.get("source_tool"):
            return str(item["source_tool"])
    return ""


def _relationship_entity_source_tool(relationship: dict, entities: list[dict]) -> str:
    endpoints = {
        str(relationship.get("from_value") or ""),
        str(relationship.get("to_value") or ""),
    }
    for item in entities:
        if str(item.get("value") or "") in endpoints and item.get("source_tool"):
            return str(item["source_tool"])
    return ""


def _relationship_source_node(
    relationship: dict,
    evidence_items: list[dict],
    entities: list[dict],
    value_to_node: dict[str, str],
    add_source_node,
) -> str | None:
    source_tool = str(relationship.get("source_tool") or "").strip()
    if not source_tool:
        source_tool = _relationship_source_tool(relationship, evidence_items)
    if not source_tool:
        source_tool = _relationship_entity_source_tool(relationship, entities)
    source_node = add_source_node(source_tool)
    if source_node:
        return source_node
    for value in (relationship.get("from_value"), relationship.get("to_value")):
        if str(value or "") in value_to_node:
            continue
    return None


def _source_kind(source_tool: str) -> str:
    lowered = source_tool.lower()
    if any(token in lowered for token in ("website", "official", "contacto")):
        return "official_web"
    if any(token in lowered for token in ("linkedin", "maigret", "social", "profile")):
        return "social"
    if any(token in lowered for token in ("directory", "dnb", "chamber", "records")):
        return "public_record"
    return "tool"


def _admiralty_confidence(code: str) -> float:
    reliability = str(code or "")[:1].upper()
    return {
        "A": 0.9,
        "B": 0.78,
        "C": 0.62,
        "D": 0.45,
        "E": 0.25,
        "F": 0.1,
    }.get(reliability, 0.0)


def _entity_type_from_predicate(predicate: str) -> str:
    lowered = str(predicate or "").lower()
    if "email" in lowered:
        return "email"
    if "phone" in lowered or "telephone" in lowered:
        return "phone"
    if "contact" in lowered:
        return "contact"
    if "business" in lowered or "product" in lowered or "scope" in lowered:
        return "business_scope"
    if "branch" in lowered or "subsidiary" in lowered:
        return "organization"
    if "address" in lowered or "location" in lowered:
        return "address"
    return "fact_object"
