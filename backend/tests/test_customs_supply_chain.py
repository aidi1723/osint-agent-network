"""
海关供应链工具单元测试
"""
import unittest
from unittest.mock import Mock, patch

from app.tools.customs_supply_chain import CustomsSupplyChainAdapter, TradePartner


class TestCustomsSupplyChainAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = CustomsSupplyChainAdapter(lookback_days=730)

    def test_validate_target(self):
        """测试目标验证"""
        # 正常公司名
        result = self.adapter.validate_target("company", "Test Company Ltd")
        self.assertEqual(result, "Test Company Ltd")

        # 错误的目标类型
        with self.assertRaises(ValueError):
            self.adapter.validate_target("domain", "example.com")

    def test_parse_trade_partners_empty(self):
        """测试空响应解析"""
        response = {"data": {"list": []}}
        partners = self.adapter._parse_trade_partners(response, "buyer", "customer")
        self.assertEqual(len(partners), 0)

    def test_parse_trade_partners_single(self):
        """测试单个交易伙伴解析"""
        response = {
            "data": {
                "list": [
                    {
                        "buyer": "Test Customer Inc",
                        "buyerCountry": "US",
                        "product": "Aluminum Profiles",
                        "tradeDate": "2024-05-15",
                        "quantity": "1000"
                    }
                ]
            }
        }

        partners = self.adapter._parse_trade_partners(response, "buyer", "customer")

        self.assertEqual(len(partners), 1)
        self.assertEqual(partners[0].name, "Test Customer Inc")
        self.assertEqual(partners[0].country, "US")
        self.assertEqual(partners[0].trade_count, 1)
        self.assertIn("Aluminum Profiles", partners[0].products)

    def test_parse_trade_partners_multiple_trades(self):
        """测试多次交易聚合"""
        response = {
            "data": {
                "list": [
                    {
                        "buyer": "Test Customer Inc",
                        "buyerCountry": "US",
                        "product": "Product A",
                        "tradeDate": "2024-05-15",
                    },
                    {
                        "buyer": "Test Customer Inc",
                        "buyerCountry": "US",
                        "product": "Product B",
                        "tradeDate": "2024-06-20",
                    },
                    {
                        "buyer": "Another Customer",
                        "buyerCountry": "CA",
                        "product": "Product C",
                        "tradeDate": "2024-04-10",
                    }
                ]
            }
        }

        partners = self.adapter._parse_trade_partners(response, "buyer", "customer")

        # 应该有2个客户
        self.assertEqual(len(partners), 2)

        # 第一个客户有2次交易
        first = [p for p in partners if p.name == "Test Customer Inc"][0]
        self.assertEqual(first.trade_count, 2)
        self.assertEqual(len(first.products), 2)

    def test_calculate_confidence(self):
        """测试置信度计算"""
        self.assertEqual(self.adapter._calculate_confidence(1), 0.70)
        self.assertEqual(self.adapter._calculate_confidence(3), 0.80)
        self.assertEqual(self.adapter._calculate_confidence(8), 0.85)
        self.assertEqual(self.adapter._calculate_confidence(15), 0.90)

    @patch('app.tools.customs_supply_chain.UpkuajingCustomsClient')
    def test_find_downstream_customers_success(self, mock_client_class):
        """测试下游客户查询成功"""
        mock_client = Mock()
        mock_client.trade_list.return_value = {
            "data": {
                "list": [
                    {
                        "buyer": "Customer A",
                        "buyerCountry": "US",
                        "product": "Test Product",
                        "tradeDate": "2024-05-15",
                    }
                ]
            }
        }
        mock_client_class.return_value = mock_client

        adapter = CustomsSupplyChainAdapter()
        customers, response = adapter.find_downstream_customers("Test Supplier")

        self.assertEqual(len(customers), 1)
        self.assertEqual(customers[0].name, "Customer A")
        self.assertTrue("data" in response)

    @patch('app.tools.customs_supply_chain.UpkuajingCustomsClient')
    def test_find_downstream_customers_api_error(self, mock_client_class):
        """测试API错误处理"""
        from app.core.upkuajing_customs import UpkuajingCustomsError

        mock_client = Mock()
        mock_client.trade_list.side_effect = UpkuajingCustomsError("API Error", 502)
        mock_client_class.return_value = mock_client

        adapter = CustomsSupplyChainAdapter()

        with self.assertRaises(UpkuajingCustomsError) as raised:
            adapter.find_downstream_customers("Test Supplier")

        self.assertEqual(raised.exception.status, 502)

    @patch('app.tools.customs_supply_chain.UpkuajingCustomsClient')
    def test_analyze_full_supply_chain(self, mock_client_class):
        """测试完整供应链分析"""
        mock_client = Mock()
        mock_client.trade_list.return_value = {
            "data": {
                "list": [
                    {
                        "buyer": "Customer A",
                        "buyerCountry": "US",
                        "product": "Product 1",
                        "tradeDate": "2024-05-15",
                    }
                ]
            }
        }
        mock_client_class.return_value = mock_client

        adapter = CustomsSupplyChainAdapter()
        result = adapter.analyze_full_supply_chain("Test Company")

        # 检查返回结构
        self.assertEqual(result.tool, "customs_supply_chain")
        self.assertEqual(result.target_type, "company")
        self.assertGreater(len(result.entities), 0)
        self.assertGreater(len(result.relationships), 0)


if __name__ == "__main__":
    unittest.main()
