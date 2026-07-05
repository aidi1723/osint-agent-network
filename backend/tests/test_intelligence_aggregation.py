import unittest

from app.core.product_intelligence import ProductIntelligenceAggregator
from app.core.social_intelligence import SocialIntelligenceAggregator


class ProductIntelligenceAggregationTests(unittest.TestCase):
    def test_trade_relationship_evidence_contributes_products(self):
        aggregator = ProductIntelligenceAggregator()

        result = aggregator.aggregate_from_data(
            entities=[],
            evidence=[
                {
                    "evidence_kind": "trade_relationship",
                    "source_tool": "customs_supply_chain",
                    "snippet": "海关记录显示3次交易，产品：Aluminum Profiles, Steel Parts...",
                }
            ],
        )

        product_names = {product.name for product in result.products}
        self.assertIn("Aluminum Profiles", product_names)
        self.assertIn("Steel Parts", product_names)
        self.assertEqual(result.total_products, 2)


class SocialIntelligenceAggregationTests(unittest.TestCase):
    def test_profile_metadata_entities_enrich_profiles_through_relationships(self):
        aggregator = SocialIntelligenceAggregator()

        result = aggregator.aggregate_from_entities(
            entities=[
                {
                    "type": "profile_url",
                    "value": "https://github.com/admin",
                    "source_tool": "maigret",
                    "confidence": 0.4,
                },
                {
                    "type": "bio_snippet",
                    "value": "Open source builder in Singapore",
                    "source_tool": "maigret",
                    "confidence": 0.3,
                },
                {
                    "type": "declared_location",
                    "value": "Singapore",
                    "source_tool": "maigret",
                    "confidence": 0.3,
                },
                {
                    "type": "profile_image_url",
                    "value": "https://avatars.githubusercontent.com/u/1",
                    "source_tool": "maigret",
                    "confidence": 0.3,
                },
                {
                    "type": "external_link",
                    "value": "https://admin.example.com",
                    "source_tool": "maigret",
                    "confidence": 0.3,
                },
            ],
            evidence=[
                {
                    "entity_value": "Open source builder in Singapore",
                    "evidence_kind": "public_profile_metadata",
                    "source_tool": "maigret",
                    "snippet": "Public profile metadata from https://github.com/admin",
                }
            ],
            relationships=[
                {
                    "from_value": "https://github.com/admin",
                    "to_value": "Open source builder in Singapore",
                    "relationship_type": "profile_has_bio_snippet",
                    "confidence": 0.3,
                },
                {
                    "from_value": "https://github.com/admin",
                    "to_value": "Singapore",
                    "relationship_type": "profile_has_declared_location",
                    "confidence": 0.3,
                },
                {
                    "from_value": "https://github.com/admin",
                    "to_value": "https://avatars.githubusercontent.com/u/1",
                    "relationship_type": "profile_has_profile_image_url",
                    "confidence": 0.3,
                },
                {
                    "from_value": "https://github.com/admin",
                    "to_value": "https://admin.example.com",
                    "relationship_type": "profile_has_external_link",
                    "confidence": 0.3,
                },
            ],
        )

        self.assertEqual(len(result.profiles), 1)
        profile = result.profiles[0]
        self.assertEqual(profile.bio, "Open source builder in Singapore")
        self.assertEqual(profile.location, "Singapore")
        self.assertEqual(profile.avatar_url, "https://avatars.githubusercontent.com/u/1")
        self.assertEqual(profile.external_links, ["https://admin.example.com"])


if __name__ == "__main__":
    unittest.main()
