import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.store import MemoryStore, SQLiteStore


class InvestigationGraphTests(unittest.TestCase):
    def test_memory_detail_includes_graph_nodes_and_edges(self):
        store = MemoryStore()
        investigation = _seed_graph_investigation(store)

        detail = store.get_investigation(investigation.id)
        graph = detail["graph"]
        node_types = {node["type"] for node in graph["nodes"]}
        edge_types = {edge["type"] for edge in graph["edges"]}
        labels = {node["label"] for node in graph["nodes"]}

        self.assertIn("seed", node_types)
        self.assertIn("entity", node_types)
        self.assertIn("evidence", node_types)
        self.assertIn("risk_signal", node_types)
        self.assertIn("username_has_social_profile", edge_types)
        self.assertIn("supports_entity", edge_types)
        self.assertIn("risk_supported_by", edge_types)
        self.assertIn("admin", labels)
        self.assertIn("https://github.com/admin", labels)
        self.assertGreaterEqual(graph["summary"]["risk_nodes"], 1)
        self.assertGreaterEqual(graph["summary"]["evidence_nodes"], 1)

    def test_sqlite_detail_persists_and_derives_graph(self):
        with TemporaryDirectory() as tmpdir:
            store = SQLiteStore(str(Path(tmpdir) / "osint.sqlite"))
            investigation = _seed_graph_investigation(store)

            graph = SQLiteStore(str(Path(tmpdir) / "osint.sqlite")).get_investigation(
                investigation.id
            )["graph"]

        self.assertGreaterEqual(graph["summary"]["nodes"], 5)
        self.assertGreaterEqual(graph["summary"]["edges"], 4)
        self.assertTrue(
            any(edge["type"] == "profile_has_declared_location" for edge in graph["edges"])
        )

    def test_risk_signal_without_matching_evidence_links_to_seed(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="admin 社媒调查",
            seed_type="username",
            seed_value="admin",
            strategy_name="standard",
        )
        store.save_risk_report(
            investigation.id,
            {
                "top_risk_signals": [
                    {
                        "kind": "weak_public_footprint",
                        "severity": "medium",
                        "summary": "No matching public profile found.",
                        "evidence_values": [],
                    }
                ]
            },
        )

        graph = store.get_investigation(investigation.id)["graph"]

        self.assertTrue(any(node["type"] == "risk_signal" for node in graph["nodes"]))
        self.assertTrue(any(edge["type"] == "risk_attached_to_seed" for edge in graph["edges"]))

    def test_graph_includes_standard_source_chain_for_evidence_and_relationships(self):
        store = MemoryStore()
        investigation = _seed_graph_investigation(store)

        graph = store.get_investigation(investigation.id)["graph"]
        source_nodes = [node for node in graph["nodes"] if node["type"] == "source"]
        edge_types = {edge["type"] for edge in graph["edges"]}

        self.assertTrue(any(node["label"] == "maigret" for node in source_nodes))
        self.assertTrue(any(node["label"] == "profile_parser" for node in source_nodes))
        self.assertIn("source_emitted_entity", edge_types)
        self.assertIn("source_emitted_evidence", edge_types)
        self.assertIn("supports_relationship", edge_types)
        self.assertTrue(
            any(
                edge["label"] == "关系来源"
                and edge["source"] in {"maigret", "profile_parser"}
                for edge in graph["edges"]
            )
        )

    def test_decision_maker_public_attributes_keep_source_chain(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="决策人画像",
            seed_type="username",
            seed_value="faizchaudhry",
            strategy_name="standard",
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="identity",
            value="Sample Contact",
            source_tool="Alibaba 客户页截图",
            confidence=0.82,
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="gender_claim",
            value="男性，公开称谓旁证",
            source_tool="BBB public profile",
            confidence=0.65,
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="age_range",
            value="35-45，公开履历区间推断",
            source_tool="public career timeline",
            confidence=0.55,
        )
        store.add_evidence(
            investigation_id=investigation.id,
            entity_value="男性，公开称谓旁证",
            evidence_kind="public_personal_attribute",
            source_tool="BBB public profile",
            snippet="Public profile uses a male-coded title; do not infer from photo or name.",
        )
        store.add_evidence(
            investigation_id=investigation.id,
            entity_value="35-45，公开履历区间推断",
            evidence_kind="public_personal_attribute",
            source_tool="public career timeline",
            snippet="Age range is estimated from public career dates, not exact birth data.",
        )
        store.add_relationship(
            investigation_id=investigation.id,
            from_value="Sample Contact",
            to_value="男性，公开称谓旁证",
            relationship_type="person_has_public_gender_claim",
            confidence=0.65,
        )
        store.add_relationship(
            investigation_id=investigation.id,
            from_value="Sample Contact",
            to_value="35-45，公开履历区间推断",
            relationship_type="person_has_public_age_range",
            confidence=0.55,
        )

        graph = store.get_investigation(investigation.id)["graph"]
        entity_types = {
            node["metadata"].get("entity_type")
            for node in graph["nodes"]
            if node["type"] == "entity"
        }
        evidence_kinds = {
            node["metadata"].get("evidence_kind")
            for node in graph["nodes"]
            if node["type"] == "evidence"
        }
        edge_types = {edge["type"] for edge in graph["edges"]}

        self.assertIn("gender_claim", entity_types)
        self.assertIn("age_range", entity_types)
        self.assertIn("public_personal_attribute", evidence_kinds)
        self.assertIn("person_has_public_gender_claim", edge_types)
        self.assertIn("person_has_public_age_range", edge_types)
        self.assertTrue(any(edge["type"] == "source_emitted_evidence" for edge in graph["edges"]))
        self.assertTrue(any(edge["type"] == "supports_entity" for edge in graph["edges"]))

    def test_enterprise_memory_preserves_non_slot_findings_and_collection_gaps(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="SampleCo 企业公开情报",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="organization",
            value="SAMPLE INTERNATIONAL TRADE CO., LTD",
            source_tool="official_web",
            confidence=0.86,
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="product_scope",
            value="Power, transmission, suspension, brake and steering systems",
            source_tool="official_web",
            confidence=0.74,
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="production_base",
            value="China Ningbo Cixi Shock Absorber Production Base",
            source_tool="official_web",
            confidence=0.78,
        )
        store.add_entity(
            investigation_id=investigation.id,
            entity_type="market_coverage",
            value="150+ countries and regions",
            source_tool="official_web",
            confidence=0.72,
        )
        store.add_relationship(
            investigation_id=investigation.id,
            from_value="Sample Auto Parts Co.",
            to_value="China Ningbo Cixi Shock Absorber Production Base",
            relationship_type="brand_claims_production_base",
            confidence=0.78,
        )

        detail = store.get_investigation(investigation.id)
        memory = detail["intelligence_memory"]

        self.assertIn("confirmed_findings", memory)
        self.assertIn("collection_gaps", memory)
        self.assertIn("directed_collection", memory)
        self.assertEqual(memory["coverage"]["confirmed_entities"], 4)
        self.assertTrue(
            any(item["type"] == "product_scope" for item in memory["confirmed_findings"])
        )
        self.assertTrue(
            any(item["type"] == "production_base" for item in memory["confirmed_findings"])
        )
        self.assertTrue(
            any(gap["key"] == "decision_maker" for gap in memory["collection_gaps"])
        )
        self.assertTrue(
            any(gap["key"] == "news" for gap in memory["collection_gaps"])
        )
        self.assertGreaterEqual(detail["graph"]["summary"]["memory_findings"], 4)

    def test_core_v2_facts_and_evidence_ledger_are_visible_in_graph(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="SampleCo Core v2 图谱",
            seed_type="company",
            seed_value="Sample Auto Parts Co.",
            strategy_name="deep",
        )
        evidence = store.add_evidence_record(
            investigation_id=investigation.id,
            source_url="https://www.example-target.test/en/",
            source_type="official_website",
            source_tool="official_web",
            snippet="SampleCo contact page lists xs@csituo.com.",
            credibility=0.82,
        )
        store.add_fact(
            investigation_id=investigation.id,
            statement="SampleCo uses xs@csituo.com as a public contact email.",
            subject="Sample Auto Parts Co.",
            predicate="uses_contact_email",
            object_value="xs@csituo.com",
            status="CONFIRMED",
            confidence=0.82,
            admiralty_code=evidence["admiralty_code"],
            evidence_ids=[evidence["id"]],
        )
        store.add_hypothesis(investigation.id, "h1", "SampleCo is an active export brand network.")
        store.score_hypotheses(
            investigation.id,
            [
                {
                    "id": "ev-export",
                    "summary": "MIMS exhibitor page shows SampleCo export contact.",
                    "kinds": ["company_news_report"],
                    "supports": ["h1"],
                    "contradicts": [],
                    "source_reliability": "B",
                    "credibility": 0.72,
                    "keywords": ["export"],
                }
            ],
        )

        graph = store.get_investigation(investigation.id)["graph"]
        node_types = {node["type"] for node in graph["nodes"]}
        edge_types = {edge["type"] for edge in graph["edges"]}
        values = {node["value"] for node in graph["nodes"]}

        self.assertIn("fact", node_types)
        self.assertIn("evidence_ledger", node_types)
        self.assertIn("hypothesis", node_types)
        self.assertIn("xs@csituo.com", values)
        self.assertIn("fact_has_object", edge_types)
        self.assertIn("evidence_supports_fact", edge_types)
        self.assertIn("hypothesis_attached_to_seed", edge_types)
        self.assertFalse(
            any(edge["type"] == "fact_has_object" and edge["from"] == edge["to"] for edge in graph["edges"])
        )
        object_nodes = [
            node
            for node in graph["nodes"]
            if node["type"] == "entity" and node["value"] == "xs@csituo.com"
        ]
        self.assertEqual(object_nodes[0]["metadata"]["entity_type"], "email")
        self.assertEqual(graph["summary"]["fact_nodes"], 1)
        self.assertEqual(graph["summary"]["evidence_ledger_nodes"], 1)
        self.assertEqual(graph["summary"]["hypothesis_nodes"], 1)

    def test_graph_nodes_include_osint_fusion_metadata(self):
        store = MemoryStore()
        investigation = store.create_investigation(
            name="Example dual-core OSINT",
            seed_type="domain",
            seed_value="example.com",
            strategy_name="deep",
        )
        store.add_entity(investigation.id, "subdomain", "vpn.example.com", "amass", 0.5)
        store.add_entity(investigation.id, "ip", "203.0.113.10", "amass", 0.45)
        store.add_entity(investigation.id, "profile_url", "https://github.com/admin", "sherlock", 0.35)
        store.add_evidence(
            investigation.id,
            "vpn.example.com",
            "amass_name_discovery",
            "amass",
            "Amass discovered vpn.example.com via crtsh",
        )
        store.add_evidence(
            investigation.id,
            "https://github.com/admin",
            "profile_exists",
            "sherlock",
            "Sherlock claimed profile on GitHub",
        )
        store.add_relationship(
            investigation.id,
            "example.com",
            "vpn.example.com",
            "domain_has_subdomain",
            0.5,
        )
        store.add_relationship(
            investigation.id,
            "admin",
            "https://github.com/admin",
            "username_has_profile",
            0.35,
        )

        graph = store.get_investigation(investigation.id)["graph"]
        by_value = {node["value"]: node for node in graph["nodes"]}

        self.assertEqual(by_value["vpn.example.com"]["metadata"]["core_axis"], "organization_asset")
        self.assertEqual(by_value["vpn.example.com"]["metadata"]["slot_hint"], "digital-footprint")
        self.assertEqual(by_value["vpn.example.com"]["metadata"]["review_status"], "candidate")
        self.assertEqual(by_value["https://github.com/admin"]["metadata"]["core_axis"], "decision_will")
        self.assertEqual(by_value["https://github.com/admin"]["metadata"]["slot_hint"], "persona-role")
        self.assertGreaterEqual(graph["summary"]["osint_signal_nodes"], 3)


def _seed_graph_investigation(store):
    investigation = store.create_investigation(
        name="admin 社媒调查",
        seed_type="username",
        seed_value="admin",
        strategy_name="standard",
    )
    store.add_entity(
        investigation_id=investigation.id,
        entity_type="username",
        value="admin",
        source_tool="maigret",
        confidence=0.4,
    )
    store.add_entity(
        investigation_id=investigation.id,
        entity_type="profile_url",
        value="https://github.com/admin",
        source_tool="maigret",
        confidence=0.4,
    )
    store.add_entity(
        investigation_id=investigation.id,
        entity_type="declared_location",
        value="Singapore",
        source_tool="profile_parser",
        confidence=0.3,
    )
    store.add_entity(
        investigation_id=investigation.id,
        entity_type="bio_snippet",
        value="crypto betting operator",
        source_tool="profile_parser",
        confidence=0.3,
    )
    store.add_evidence(
        investigation_id=investigation.id,
        entity_value="https://github.com/admin",
        evidence_kind="social_profile_exists",
        source_tool="maigret",
        snippet="Maigret found claimed profile on GitHub.",
    )
    store.add_relationship(
        investigation_id=investigation.id,
        from_value="admin",
        to_value="https://github.com/admin",
        relationship_type="username_has_social_profile",
        confidence=0.4,
    )
    store.add_relationship(
        investigation_id=investigation.id,
        from_value="https://github.com/admin",
        to_value="Singapore",
        relationship_type="profile_has_declared_location",
        confidence=0.3,
    )
    store.save_risk_report(
        investigation.id,
        {
            "top_risk_signals": [
                {
                    "kind": "business_risk_keyword",
                    "severity": "high",
                    "summary": "Public profile text contains configured risk keywords.",
                    "evidence_values": ["crypto betting operator"],
                }
            ]
        },
    )
    return investigation


if __name__ == "__main__":
    unittest.main()
