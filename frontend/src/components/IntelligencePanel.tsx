import React, { useState, useEffect } from "react";
import { Mail, Phone, MessageCircle, Linkedin, Users, Package, Globe, ShoppingBag, Activity } from "lucide-react";
import type { IntelligenceData, Investigation } from "../types";
import { fetchInvestigationIntelligence } from "../api";

type IntelligencePanelProps = {
  investigation: Investigation;
  apiBase: string;
  requestHeaders: () => Record<string, string> | undefined;
};

export function IntelligencePanel({ investigation, apiBase, requestHeaders }: IntelligencePanelProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<IntelligenceData | null>(null);
  const [activeTab, setActiveTab] = useState<"contacts" | "social" | "products">("contacts");

  const loadIntelligence = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchInvestigationIntelligence(apiBase, investigation.id, requestHeaders());
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "情报汇总加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (investigation.id) {
      loadIntelligence();
    }
  }, [investigation.id]);

  if (loading) {
    return (
      <div className="intelligence-panel">
        <div className="loading-state">
          <Activity className="spin" size={24} />
          <p>正在聚合情报...</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="intelligence-panel">
        <div className="error-banner">
          <span>{error}</span>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="intelligence-panel">
        <div className="empty-state">
          <Activity size={32} />
          <p>暂无情报汇总数据</p>
        </div>
      </div>
    );
  }

  const { contacts, social, products } = data;

  return (
    <div className="intelligence-panel">
      <div className="panel-header">
        <h3>情报汇总</h3>
        <button className="btn-secondary btn-small" onClick={loadIntelligence}>
          刷新
        </button>
      </div>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
        </div>
      )}

      <div className="intelligence-summary">
        <div className="summary-item">
          <Mail size={16} />
          <span>{contacts.summary.emails_count} 邮箱</span>
        </div>
        <div className="summary-item">
          <Phone size={16} />
          <span>{contacts.summary.phones_count} 电话</span>
        </div>
        <div className="summary-item">
          <Users size={16} />
          <span>{social.summary.total} 社媒</span>
        </div>
        <div className="summary-item">
          <Package size={16} />
          <span>{products.summary.total_products} 产品</span>
        </div>
      </div>

      <div className="tab-navigation">
        <button
          className={activeTab === "contacts" ? "tab-active" : "tab-inactive"}
          onClick={() => setActiveTab("contacts")}
        >
          <Mail size={16} />
          联系方式 ({contacts.summary.total})
        </button>
        <button
          className={activeTab === "social" ? "tab-active" : "tab-inactive"}
          onClick={() => setActiveTab("social")}
        >
          <Users size={16} />
          社交媒体 ({social.summary.total})
        </button>
        <button
          className={activeTab === "products" ? "tab-active" : "tab-inactive"}
          onClick={() => setActiveTab("products")}
        >
          <Package size={16} />
          产品情报 ({products.summary.total_products})
        </button>
      </div>

      <div className="intelligence-content">
        {activeTab === "contacts" && <ContactsView data={contacts} />}
        {activeTab === "social" && <SocialView data={social} />}
        {activeTab === "products" && <ProductsView data={products} />}
      </div>
    </div>
  );
}

function ContactsView({ data }: { data: IntelligenceData["contacts"] }) {
  return (
    <div className="contacts-view">
      {data.emails.length > 0 && (
        <section className="contact-section">
          <h4>
            <Mail size={16} />
            邮箱地址 ({data.emails.length})
          </h4>
          <div className="contact-list">
            {data.emails.map((email, idx) => (
              <div key={idx} className="contact-item">
                <div className="contact-value">
                  <a href={`mailto:${email.value}`}>{email.value}</a>
                  {email.verified && <span className="badge verified">已验证</span>}
                </div>
                <div className="contact-meta">
                  <span className="source">来源: {email.source}</span>
                  <span className="confidence">置信度: {(email.confidence * 100).toFixed(0)}%</span>
                </div>
                {email.context && <div className="contact-context">{email.context}</div>}
              </div>
            ))}
          </div>
        </section>
      )}

      {data.phones.length > 0 && (
        <section className="contact-section">
          <h4>
            <Phone size={16} />
            电话号码 ({data.phones.length})
          </h4>
          <div className="contact-list">
            {data.phones.map((phone, idx) => (
              <div key={idx} className="contact-item">
                <div className="contact-value">
                  <a href={`tel:${phone.value}`}>{phone.value}</a>
                </div>
                <div className="contact-meta">
                  <span className="source">来源: {phone.source}</span>
                  <span className="confidence">置信度: {(phone.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {data.social.length > 0 && (
        <section className="contact-section">
          <h4>
            <MessageCircle size={16} />
            社交联系 ({data.social.length})
          </h4>
          <div className="contact-list">
            {data.social.map((contact, idx) => (
              <div key={idx} className="contact-item">
                <div className="contact-value">
                  <span className="contact-type">{contact.type}</span>
                  <span>{contact.value}</span>
                </div>
                <div className="contact-meta">
                  <span className="source">来源: {contact.source}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {data.websites.length > 0 && (
        <section className="contact-section">
          <h4>
            <Globe size={16} />
            网站 ({data.websites.length})
          </h4>
          <div className="website-list">
            {data.websites.map((url, idx) => (
              <a key={idx} href={url} target="_blank" rel="noopener noreferrer" className="website-link">
                {url}
              </a>
            ))}
          </div>
        </section>
      )}

      {data.summary.total === 0 && (
        <div className="empty-state">
          <Mail size={48} />
          <p>未发现联系方式</p>
        </div>
      )}
    </div>
  );
}

function SocialView({ data }: { data: IntelligenceData["social"] }) {
  if (data.profiles.length === 0) {
    return (
      <div className="empty-state">
        <Users size={48} />
        <p>未发现社交媒体账号</p>
      </div>
    );
  }

  return (
    <div className="social-view">
      <div className="social-stats">
        <div className="stat-chip">职业平台: {data.summary.professional}</div>
        <div className="stat-chip">个人平台: {data.summary.personal}</div>
        <div className="stat-chip">公开平台: {data.summary.public}</div>
      </div>

      <div className="profile-list">
        {data.profiles.map((profile, idx) => (
          <div key={idx} className="profile-card">
            <div className="profile-header">
              <div className="profile-icon">
                <Linkedin size={20} />
              </div>
              <div className="profile-info">
                <div className="profile-platform">{profile.platform}</div>
                <a href={profile.url} target="_blank" rel="noopener noreferrer" className="profile-username">
                  @{profile.username}
                </a>
              </div>
              {profile.verified && <span className="badge verified">已验证</span>}
            </div>

            {profile.display_name && <div className="profile-name">{profile.display_name}</div>}

            {profile.bio && <div className="profile-bio">{profile.bio}</div>}

            {profile.location && (
              <div className="profile-location">
                <Globe size={14} />
                {profile.location}
              </div>
            )}

            {profile.followers && (
              <div className="profile-followers">
                <Users size={14} />
                {profile.followers.toLocaleString()} 关注者
              </div>
            )}

            <div className="profile-meta">
              <span className="source">来源: {profile.source}</span>
              <span className="confidence">置信度: {(profile.confidence * 100).toFixed(0)}%</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ProductsView({ data }: { data: IntelligenceData["products"] }) {
  if (data.products.length === 0) {
    return (
      <div className="empty-state">
        <Package size={48} />
        <p>未发现产品信息</p>
      </div>
    );
  }

  return (
    <div className="products-view">
      {data.main_products.length > 0 && (
        <section className="products-section">
          <h4>
            <ShoppingBag size={16} />
            主营产品
          </h4>
          <div className="main-products-grid">
            {data.main_products.map((product, idx) => (
              <div key={idx} className="main-product-card">
                <div className="product-name">{product.name}</div>
                {product.category && <div className="product-category">{product.category}</div>}
                <div className="product-stats">
                  <span>提及 {product.mention_count} 次</span>
                  <span className="confidence">{(product.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {data.categories.length > 0 && (
        <section className="products-section">
          <h4>产品类别</h4>
          <div className="category-tags">
            {data.categories.map((cat, idx) => (
              <span key={idx} className="category-tag">
                {cat}
              </span>
            ))}
          </div>
        </section>
      )}

      {data.products.length > 0 && (
        <section className="products-section">
          <h4>全部产品 ({data.products.length})</h4>
          <div className="product-list">
            {data.products.map((product, idx) => (
              <div key={idx} className="product-item">
                <div className="product-header">
                  <span className="product-name">{product.name}</span>
                  {product.hs_code && <span className="hs-code">HS: {product.hs_code}</span>}
                </div>
                {product.category && <div className="product-category">{product.category}</div>}
                <div className="product-meta">
                  <span>来源: {product.source}</span>
                  <span>提及 {product.mention_count} 次</span>
                  <span>置信度: {(product.confidence * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
