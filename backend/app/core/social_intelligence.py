"""
社媒情报聚合工具

整合Sherlock、Maigret等工具的输出，统一展示社交媒体情报：
- 社交平台账号
- 个人资料信息
- 活动痕迹
- 关联账号
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import re


@dataclass
class SocialProfile:
    """社交媒体档案"""
    platform: str  # linkedin, facebook, twitter, instagram, etc.
    username: str
    profile_url: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    followers: Optional[int] = None
    verified: bool = False
    avatar_url: Optional[str] = None
    external_links: list[str] = None
    last_active: Optional[str] = None
    source_tool: str = ''
    confidence: float = 0.0

    def __post_init__(self):
        if self.external_links is None:
            self.external_links = []


@dataclass
class SocialIntelligenceResult:
    """社媒情报结果"""
    target: str
    profiles: list[SocialProfile]
    platforms_found: list[str]
    total_profiles: int
    professional_profiles: list[SocialProfile]  # LinkedIn等职业平台
    personal_profiles: list[SocialProfile]  # Facebook, Instagram等
    public_profiles: list[SocialProfile]  # Twitter, YouTube等


class SocialIntelligenceAggregator:
    """社媒情报聚合器"""

    PROFESSIONAL_PLATFORMS = {'linkedin', 'github', 'stackoverflow', 'angellist'}
    PERSONAL_PLATFORMS = {'facebook', 'instagram', 'snapchat', 'tiktok'}
    PUBLIC_PLATFORMS = {'twitter', 'youtube', 'medium', 'reddit'}

    def aggregate_from_entities(
        self,
        entities: list[dict],
        evidence: list[dict],
        relationships: list[dict]
    ) -> SocialIntelligenceResult:
        """
        从实体、证据、关系中聚合社媒情报

        Args:
            entities: 实体列表
            evidence: 证据列表
            relationships: 关系列表

        Returns:
            SocialIntelligenceResult
        """
        profiles = []

        # 从实体中提取profile_url
        for entity in entities:
            entity_type = entity.get('type', '')
            value = entity.get('value', '')
            source_tool = entity.get('source_tool', 'unknown')
            confidence = float(entity.get('confidence', 0.5))

            if entity_type == 'profile_url':
                platform = self._detect_platform(value)
                username = self._extract_username(value, platform)

                profiles.append(SocialProfile(
                    platform=platform,
                    username=username,
                    profile_url=value,
                    source_tool=source_tool,
                    confidence=confidence
                ))

        # 从证据中提取额外信息
        for profile in profiles:
            self._enrich_profile_from_evidence(profile, evidence)
            self._enrich_profile_from_relationships(profile, entities, relationships)

        # 去重
        profiles = self._deduplicate_profiles(profiles)

        # 分类
        professional = [p for p in profiles if p.platform in self.PROFESSIONAL_PLATFORMS]
        personal = [p for p in profiles if p.platform in self.PERSONAL_PLATFORMS]
        public = [p for p in profiles if p.platform in self.PUBLIC_PLATFORMS]

        platforms_found = list(set(p.platform for p in profiles))

        return SocialIntelligenceResult(
            target='',
            profiles=profiles,
            platforms_found=platforms_found,
            total_profiles=len(profiles),
            professional_profiles=professional,
            personal_profiles=personal,
            public_profiles=public
        )

    def _detect_platform(self, url: str) -> str:
        """从URL检测社交平台"""
        url_lower = url.lower()

        platform_patterns = {
            'linkedin': ['linkedin.com'],
            'facebook': ['facebook.com', 'fb.com'],
            'twitter': ['twitter.com', 'x.com'],
            'instagram': ['instagram.com'],
            'github': ['github.com'],
            'youtube': ['youtube.com'],
            'tiktok': ['tiktok.com'],
            'reddit': ['reddit.com'],
            'medium': ['medium.com'],
            'stackoverflow': ['stackoverflow.com'],
            'angellist': ['angel.co', 'angellist.com'],
            'pinterest': ['pinterest.com'],
            'snapchat': ['snapchat.com'],
            'telegram': ['t.me', 'telegram.me'],
            'whatsapp': ['wa.me', 'whatsapp.com'],
        }

        for platform, patterns in platform_patterns.items():
            if any(p in url_lower for p in patterns):
                return platform

        return 'unknown'

    def _extract_username(self, url: str, platform: str) -> str:
        """从URL提取用户名"""
        # 简化版本，实际可以根据不同平台优化
        parts = url.rstrip('/').split('/')
        if len(parts) >= 2:
            # 通常用户名是最后一部分或倒数第二部分
            username = parts[-1]
            if username and username not in {'', 'profile', 'user'}:
                return username
            elif len(parts) >= 3:
                return parts[-2]
        return 'unknown'

    def _enrich_profile_from_evidence(self, profile: SocialProfile, evidence: list[dict]):
        """从证据中补充profile信息"""
        for ev in evidence:
            entity_value = ev.get('entity_value', '')
            if entity_value != profile.profile_url:
                continue

            evidence_kind = ev.get('evidence_kind', '')
            snippet = ev.get('snippet', '')

            if evidence_kind == 'bio_snippet':
                profile.bio = snippet
            elif evidence_kind == 'declared_location':
                profile.location = snippet
            elif evidence_kind == 'profile_image_url':
                profile.avatar_url = snippet
            elif evidence_kind == 'external_link':
                if snippet not in profile.external_links:
                    profile.external_links.append(snippet)

    def _enrich_profile_from_relationships(
        self,
        profile: SocialProfile,
        entities: list[dict],
        relationships: list[dict],
    ):
        """从 profile_has_* 关系补充 Maigret/Profile Parser 元数据。"""
        entity_by_value = {entity.get('value', ''): entity for entity in entities}
        for relationship in relationships:
            if relationship.get('from_value') != profile.profile_url:
                continue
            linked_value = relationship.get('to_value', '')
            linked_entity = entity_by_value.get(linked_value, {})
            entity_type = linked_entity.get('type', '')
            relationship_type = relationship.get('relationship_type', '')

            if entity_type == 'bio_snippet' or relationship_type == 'profile_has_bio_snippet':
                profile.bio = linked_value
            elif entity_type == 'declared_location' or relationship_type == 'profile_has_declared_location':
                profile.location = linked_value
            elif entity_type == 'profile_image_url' or relationship_type == 'profile_has_profile_image_url':
                profile.avatar_url = linked_value
            elif entity_type == 'external_link' or relationship_type == 'profile_has_external_link':
                if linked_value and linked_value not in profile.external_links:
                    profile.external_links.append(linked_value)

    def _deduplicate_profiles(self, profiles: list[SocialProfile]) -> list[SocialProfile]:
        """去重profile，同一平台同一用户名只保留一个"""
        seen = {}
        for profile in profiles:
            key = (profile.platform, profile.username.lower())
            if key not in seen or profile.confidence > seen[key].confidence:
                seen[key] = profile

        result = list(seen.values())
        result.sort(key=lambda p: p.confidence, reverse=True)
        return result

    def format_for_display(self, result: SocialIntelligenceResult) -> dict:
        """格式化为前端显示格式"""
        def profile_to_dict(p: SocialProfile) -> dict:
            return {
                'platform': p.platform,
                'username': p.username,
                'url': p.profile_url,
                'display_name': p.display_name,
                'bio': p.bio,
                'location': p.location,
                'followers': p.followers,
                'verified': p.verified,
                'avatar_url': p.avatar_url,
                'external_links': p.external_links,
                'source': p.source_tool,
                'confidence': p.confidence
            }

        return {
            'target': result.target,
            'profiles': [profile_to_dict(p) for p in result.profiles],
            'platforms': result.platforms_found,
            'summary': {
                'total': result.total_profiles,
                'professional': len(result.professional_profiles),
                'personal': len(result.personal_profiles),
                'public': len(result.public_profiles)
            },
            'by_category': {
                'professional': [profile_to_dict(p) for p in result.professional_profiles],
                'personal': [profile_to_dict(p) for p in result.personal_profiles],
                'public': [profile_to_dict(p) for p in result.public_profiles]
            }
        }
