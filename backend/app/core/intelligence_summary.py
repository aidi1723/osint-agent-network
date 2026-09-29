from __future__ import annotations


_EMAIL = "email"
_PHONE = "phone"
_WEBSITE_TYPES = {"domain", "website", "url", "official_website"}
_PRODUCT_TYPES = {"business_scope", "product_scope", "purchase_category", "product"}
_SOCIAL_TYPES = {
    "username",
    "profile_url",
    "social",
    "linkedin",
    "twitter",
    "x",
    "facebook",
    "instagram",
    "tiktok",
    "weibo",
    "wechat",
    "whatsapp",
    "telegram",
}
_PROFESSIONAL = {"linkedin"}
_PERSONAL = {"twitter", "x", "facebook", "instagram", "tiktok", "weibo"}
_HANDLE_TYPES = {"whatsapp", "telegram", "wechat", "username"}


def build_investigation_intelligence(detail: dict) -> dict:
    entities = list(detail.get("entities") or [])
    snippets = _snippets_by_value(detail)
    emails: list[dict] = []
    phones: list[dict] = []
    contact_social: list[dict] = []
    websites: list[str] = []
    profiles: list[dict] = []
    products: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for entity in entities:
        entity_type = str(entity.get("type") or "").strip().lower()
        value = str(entity.get("value") or "").strip()
        if not entity_type or not value:
            continue
        key = (entity_type, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        source = str(entity.get("source_tool") or "")
        confidence = _confidence(entity.get("confidence"))
        context = snippets.get(value.casefold(), "")
        if entity_type == _EMAIL:
            emails.append(
                {
                    "value": value,
                    "source": source,
                    "confidence": confidence,
                    "verified": confidence >= 0.8,
                    "context": context,
                }
            )
        elif entity_type == _PHONE:
            phones.append(
                {
                    "value": value,
                    "source": source,
                    "confidence": confidence,
                    "verified": confidence >= 0.8,
                    "context": context,
                }
            )
        elif entity_type in _WEBSITE_TYPES:
            websites.append(_as_url(value))
        elif entity_type in _PRODUCT_TYPES:
            products.append(
                {
                    "name": value,
                    "source": source,
                    "mention_count": 1,
                    "confidence": confidence,
                    "contexts": [context] if context else [],
                }
            )
        elif entity_type in _SOCIAL_TYPES:
            if entity_type in _HANDLE_TYPES and not value.startswith(("http://", "https://")):
                contact_social.append(
                    {
                        "type": entity_type,
                        "value": value,
                        "source": source,
                        "confidence": confidence,
                        "context": context,
                    }
                )
            else:
                profiles.append(_profile(entity_type, value, source, confidence))

    categories = sorted({item["name"] for item in products})
    platforms = sorted({item["platform"] for item in profiles})
    return {
        "investigation_id": str(detail.get("id") or ""),
        "contacts": {
            "emails": emails,
            "phones": phones,
            "social": contact_social,
            "websites": websites,
            "summary": {
                "total": len(emails) + len(phones) + len(contact_social) + len(websites),
                "emails_count": len(emails),
                "phones_count": len(phones),
                "social_count": len(contact_social),
                "websites_count": len(websites),
            },
        },
        "social": {
            "profiles": profiles,
            "platforms": platforms,
            "summary": {
                "total": len(profiles),
                "professional": sum(1 for item in profiles if item["platform"] in _PROFESSIONAL),
                "personal": sum(1 for item in profiles if item["platform"] in _PERSONAL),
                "public": sum(
                    1 for item in profiles if item["platform"] not in _PROFESSIONAL | _PERSONAL
                ),
            },
        },
        "products": {
            "products": products,
            "categories": categories,
            "hs_codes": [],
            "main_products": [
                {
                    "name": item["name"],
                    "mention_count": item["mention_count"],
                    "confidence": item["confidence"],
                }
                for item in products[:5]
            ],
            "summary": {
                "total_products": len(products),
                "categories_count": len(categories),
                "hs_codes_count": 0,
                "main_products_count": min(len(products), 5),
            },
        },
    }


def _snippets_by_value(detail: dict) -> dict[str, str]:
    snippets: dict[str, str] = {}
    for record in list(detail.get("evidence") or []) + list(detail.get("evidence_ledger") or []):
        value = str(record.get("entity_value") or "").strip().casefold()
        snippet = str(record.get("snippet") or record.get("summary") or "").strip()
        if value and snippet and value not in snippets:
            snippets[value] = snippet[:240]
    return snippets


def _confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(number, 1.0))


def _as_url(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def _profile(entity_type: str, value: str, source: str, confidence: float) -> dict:
    platform = entity_type if entity_type not in {"profile_url", "social", "username"} else _platform_from_url(value)
    url = value if value.startswith(("http://", "https://")) else ""
    username = value.rsplit("/", 1)[-1] if url else value
    return {
        "platform": platform or "social",
        "username": username,
        "url": url,
        "verified": confidence >= 0.8,
        "external_links": [url] if url else [],
        "source": source,
        "confidence": confidence,
    }


def _platform_from_url(value: str) -> str:
    host = value.split("://", 1)[-1].split("/", 1)[0].removeprefix("www.").lower()
    for name in ("linkedin", "twitter", "facebook", "instagram", "tiktok"):
        if name in host:
            return name
    return "social"
