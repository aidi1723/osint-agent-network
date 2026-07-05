"""
联系方式发现聚合工具

整合多个工具的输出，统一提取和展示联系方式：
- theHarvester: 域名邮箱
- 官网解析: 联系页面
- 社媒工具: 社媒联系方式
- 海关数据: 贸易伙伴联系信息
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import re

from app.core.normalization import normalize_target


@dataclass
class ContactInfo:
    """联系方式信息"""
    contact_type: str  # email, phone, whatsapp, wechat, linkedin, skype
    value: str
    source: str  # 来源：website, social, customs, tool
    verified: bool  # 是否验证过
    confidence: float
    context: str  # 上下文（如：found on contact page）


@dataclass
class ContactDiscoveryResult:
    """联系方式发现结果"""
    target: str
    emails: list[ContactInfo]
    phones: list[ContactInfo]
    social_contacts: list[ContactInfo]  # WhatsApp, WeChat, LinkedIn, Skype
    websites: list[str]
    total_contacts: int


class ContactDiscoveryAggregator:
    """联系方式发现聚合器"""

    def __init__(self):
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.phone_pattern = re.compile(r'\+?[1-9]\d{1,14}')  # E.164格式

    def aggregate_from_entities(
        self,
        entities: list[dict],
        evidence: list[dict]
    ) -> ContactDiscoveryResult:
        """
        从实体和证据中聚合联系方式

        Args:
            entities: 实体列表
            evidence: 证据列表

        Returns:
            ContactDiscoveryResult
        """
        emails = []
        phones = []
        social_contacts = []
        websites = []

        # 从实体中提取
        for entity in entities:
            entity_type = entity.get('type', '')
            value = entity.get('value', '')
            source_tool = entity.get('source_tool', 'unknown')
            confidence = float(entity.get('confidence', 0.5))

            if entity_type == 'email':
                emails.append(ContactInfo(
                    contact_type='email',
                    value=value,
                    source=source_tool,
                    verified=False,
                    confidence=confidence,
                    context=''
                ))
            elif entity_type == 'phone':
                phones.append(ContactInfo(
                    contact_type='phone',
                    value=value,
                    source=source_tool,
                    verified=False,
                    confidence=confidence,
                    context=''
                ))
            elif entity_type == 'domain':
                websites.append(value)
            elif entity_type in {'linkedin_url', 'whatsapp', 'wechat', 'skype'}:
                social_contacts.append(ContactInfo(
                    contact_type=entity_type,
                    value=value,
                    source=source_tool,
                    verified=False,
                    confidence=confidence,
                    context=''
                ))

        # 从证据中提取额外联系方式
        for ev in evidence:
            snippet = ev.get('snippet', '')
            source_tool = ev.get('source_tool', 'unknown')

            # 提取邮箱
            found_emails = self.email_pattern.findall(snippet)
            for email in found_emails:
                if not any(c.value == email for c in emails):
                    emails.append(ContactInfo(
                        contact_type='email',
                        value=email,
                        source=source_tool,
                        verified=False,
                        confidence=0.6,
                        context=snippet[:100]
                    ))

            # 提取电话（基础版）
            found_phones = self.phone_pattern.findall(snippet)
            for phone in found_phones:
                if len(phone) >= 10 and not any(c.value == phone for c in phones):
                    phones.append(ContactInfo(
                        contact_type='phone',
                        value=phone,
                        source=source_tool,
                        verified=False,
                        confidence=0.5,
                        context=snippet[:100]
                    ))

        # 去重和排序
        emails = self._deduplicate_contacts(emails)
        phones = self._deduplicate_contacts(phones)
        social_contacts = self._deduplicate_contacts(social_contacts)
        websites = list(set(websites))

        return ContactDiscoveryResult(
            target='',
            emails=emails,
            phones=phones,
            social_contacts=social_contacts,
            websites=websites,
            total_contacts=len(emails) + len(phones) + len(social_contacts)
        )

    def _deduplicate_contacts(self, contacts: list[ContactInfo]) -> list[ContactInfo]:
        """去重联系方式，保留置信度最高的"""
        seen = {}
        for contact in contacts:
            key = contact.value.lower()
            if key not in seen or contact.confidence > seen[key].confidence:
                seen[key] = contact

        # 按置信度排序
        result = list(seen.values())
        result.sort(key=lambda c: c.confidence, reverse=True)
        return result

    def format_for_display(self, result: ContactDiscoveryResult) -> dict:
        """格式化为前端显示格式"""
        return {
            'target': result.target,
            'emails': [
                {
                    'value': c.value,
                    'source': c.source,
                    'confidence': c.confidence,
                    'verified': c.verified,
                    'context': c.context
                }
                for c in result.emails
            ],
            'phones': [
                {
                    'value': c.value,
                    'source': c.source,
                    'confidence': c.confidence,
                    'verified': c.verified,
                    'context': c.context
                }
                for c in result.phones
            ],
            'social': [
                {
                    'type': c.contact_type,
                    'value': c.value,
                    'source': c.source,
                    'confidence': c.confidence,
                    'context': c.context
                }
                for c in result.social_contacts
            ],
            'websites': result.websites,
            'summary': {
                'total': result.total_contacts,
                'emails_count': len(result.emails),
                'phones_count': len(result.phones),
                'social_count': len(result.social_contacts),
                'websites_count': len(result.websites)
            }
        }
