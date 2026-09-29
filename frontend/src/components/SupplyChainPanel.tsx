import React, { useState } from "react";
import { TrendingUp, TrendingDown, Package, MapPin, Calendar, AlertCircle } from "lucide-react";
import type { Investigation, SupplyChainData, TradePartner } from "../types";
import { createSupplyChainInvestigation, fetchSupplyChainData } from "../api";

type SupplyChainPanelProps = {
  investigation: Investigation;
  apiBase: string;
  requestHeaders: () => Record<string, string> | undefined;
};

export function SupplyChainPanel({ investigation, apiBase, requestHeaders }: SupplyChainPanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SupplyChainData | null>(null);
  const [activeTab, setActiveTab] = useState<"downstream" | "upstream">("downstream");

  const querySupplyChain = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await fetchSupplyChainData(apiBase, investigation.seed_value, requestHeaders());
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setLoading(false);
    }
  };

  const createInvestigation = async (companyName: string) => {
    setError(null);
    try {
      await createSupplyChainInvestigation(apiBase, companyName, requestHeaders());
      window.location.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建深度调查失败");
    }
  };

  return (
    <div className="supply-chain-panel">
      <div className="panel-header">
        <h3>海关供应链分析</h3>
        <button
          className="btn-primary"
          onClick={querySupplyChain}
          disabled={loading}
        >
          {loading ? "查询中..." : "分析供应链"}
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {data && (
        <>
          <div className="tab-navigation">
            <button
              className={activeTab === "downstream" ? "tab-active" : "tab-inactive"}
              onClick={() => setActiveTab("downstream")}
            >
              <TrendingDown size={16} />
              下游客户 ({data.downstream.total_count})
            </button>
            <button
              className={activeTab === "upstream" ? "tab-active" : "tab-inactive"}
              onClick={() => setActiveTab("upstream")}
            >
              <TrendingUp size={16} />
              上游供应商 ({data.upstream.total_count})
            </button>
          </div>

          <div className="supply-chain-content">
            {activeTab === "downstream" && (
              <PartnerList
                partners={data.downstream.customers}
                type="customer"
                onCreateInvestigation={createInvestigation}
              />
            )}
            {activeTab === "upstream" && (
              <PartnerList
                partners={data.upstream.suppliers}
                type="supplier"
                onCreateInvestigation={createInvestigation}
              />
            )}
          </div>

          <div className="supply-chain-summary">
            <div className="summary-card">
              <span className="summary-label">下游客户</span>
              <span className="summary-value">{data.downstream.total_count}</span>
            </div>
            <div className="summary-card">
              <span className="summary-label">上游供应商</span>
              <span className="summary-value">{data.upstream.total_count}</span>
            </div>
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div className="empty-state">
          <Package size={48} />
          <p>点击"分析供应链"查询海关贸易数据</p>
          <p className="empty-state-hint">
            将分析该公司的所有进出口记录，识别上下游贸易伙伴
          </p>
        </div>
      )}
    </div>
  );
}

type PartnerListProps = {
  partners: TradePartner[];
  type: "customer" | "supplier";
  onCreateInvestigation: (name: string) => void;
};

function PartnerList({ partners, type, onCreateInvestigation }: PartnerListProps) {
  if (partners.length === 0) {
    return (
      <div className="empty-state">
        <p>未找到{type === "customer" ? "下游客户" : "上游供应商"}数据</p>
      </div>
    );
  }

  return (
    <div className="partner-list">
      {partners.map((partner, index) => (
        <div key={`${partner.name}-${index}`} className="partner-card">
          <div className="partner-header">
            <div className="partner-name-row">
              <strong className="partner-name">{partner.name}</strong>
              <span className="partner-country">
                <MapPin size={14} />
                {partner.country}
              </span>
            </div>
            <button
              className="btn-secondary btn-small"
              onClick={() => onCreateInvestigation(partner.name)}
              title="创建深度调查任务"
            >
              深度调查
            </button>
          </div>

          <div className="partner-stats">
            <div className="stat-item">
              <span className="stat-label">交易次数</span>
              <span className="stat-value">{partner.trade_count}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">
                <Calendar size={14} />
                首次交易
              </span>
              <span className="stat-value-small">{partner.first_trade}</span>
            </div>
            <div className="stat-item">
              <span className="stat-label">
                <Calendar size={14} />
                最近交易
              </span>
              <span className="stat-value-small">{partner.last_trade}</span>
            </div>
          </div>

          {partner.products.length > 0 && (
            <div className="partner-products">
              <span className="products-label">
                <Package size={14} />
                交易产品
              </span>
              <div className="products-tags">
                {partner.products.slice(0, 5).map((product, i) => (
                  <span key={i} className="product-tag" title={product}>
                    {product.length > 30 ? product.substring(0, 30) + "..." : product}
                  </span>
                ))}
                {partner.products.length > 5 && (
                  <span className="product-tag-more">+{partner.products.length - 5}</span>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
